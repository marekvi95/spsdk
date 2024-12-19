#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2024 NXP
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module handling the operations on fuses."""

import functools
import logging
from abc import abstractmethod
from typing import Any, Callable, Optional, Type

from typing_extensions import Self

from spsdk import version as spsdk_version
from spsdk.exceptions import (
    SPSDKAttributeError,
    SPSDKError,
    SPSDKKeyError,
    SPSDKTypeError,
    SPSDKValueError,
)
from spsdk.fuses.fuse_registers import FuseLock, FuseRegister, FuseRegisters, IndividualWriteLock
from spsdk.mboot.mcuboot import McuBoot
from spsdk.utils.database import DatabaseManager, get_db, get_families, get_schema_file
from spsdk.utils.misc import Endianness, get_abs_path, value_to_int, write_file
from spsdk.utils.schema_validator import (
    CommentedConfig,
    check_config,
    update_validation_schema_family,
)

logger = logging.getLogger(__name__)


class SPSDKFuseOperationFailure(SPSDKError):
    """SPSDK Fuse operation failure."""


class SPSDKFuseConfigurationError(SPSDKError):
    """SPSDK Fuse configuration failure."""


class FuseOperator:
    """Fuse operator abstract class."""

    NAME: Optional[str] = None

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Fuse Operator {self.NAME}"

    @abstractmethod
    def read_fuse(self, index: int) -> int:
        """Read a single fuse value.

        :param index: Index of a fuse
        :return: Fuse value
        """

    @abstractmethod
    def write_fuse(self, index: int, value: int, lock: bool = False) -> None:
        """Write a single fuse.

        :param index: Index of a fuse
        :param value: Fuse value to be written
        :param lock: Lock fuse after write
        """

    @classmethod
    @abstractmethod
    def get_fuse_script(
        cls, family: str, fuses: list[FuseRegister], revision: str = "latest"
    ) -> str:
        """Get fuse script."""

    @classmethod
    @abstractmethod
    def get_fuse_write_cmd(
        cls, index: int, value: int, lock: bool = False, verify: bool = False
    ) -> str:
        """Get write command for a single fuse."""

    @classmethod
    def get_operator_type(cls, name: str) -> Type["FuseOperator"]:
        """Get operator type by its name."""
        for subclass in FuseOperator.__subclasses__():
            if subclass.NAME == name:
                return subclass
        raise SPSDKKeyError(f"No such a fuse operator with name {name}")


def mboot_operation_decorator(func: Callable) -> Callable:
    """Decorator to handle a method with mcuboot operation."""

    @functools.wraps(func)
    def wrapper(self: "BlhostFuseOperator", *args: Any, **kwargs: Any) -> Any:
        assert isinstance(self, BlhostFuseOperator)
        if not self.mboot.is_opened:
            self.mboot.open()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.mboot.close()

    return wrapper


class BlhostFuseOperator(FuseOperator):
    """Blhost fuse operator."""

    NAME = "blhost"

    def __init__(self, mboot: McuBoot):
        """Blhost fuse operator initialization."""
        self.mboot = mboot

    @mboot_operation_decorator
    def read_fuse(self, index: int) -> int:
        """Read a single fuse value.

        :param index: Index of a fuse
        :return: Fuse value
        """
        ret = self.mboot.efuse_read_once(index)
        if ret is None:
            raise SPSDKFuseOperationFailure("Reading of fuse failed.")
        return ret

    @mboot_operation_decorator
    def write_fuse(self, index: int, value: int, lock: bool = False) -> None:
        """Write a single fuse.

        :param index: Index of a fuse
        :param value: Fuse value to be written
        :param lock: Lock fuse after write
        """
        if lock:
            index = index | (1 << 24)
        ret = self.mboot.efuse_program_once(index, value)
        if not ret:
            raise SPSDKFuseOperationFailure("Writing of fuse failed.")

    @classmethod
    def get_fuse_script(
        cls, family: str, fuses: list[FuseRegister], revision: str = "latest"
    ) -> str:
        """Get fuses script."""
        ret = (
            "# BLHOST fuses programming script\n"
            f"# Generated by SPSDK {spsdk_version}\n"
            f"# Chip: {family} rev:{revision}\n\n\n"
        )
        for fuse in fuses:
            if fuse.otp_index is None:
                raise SPSDKAttributeError(f"OTP index is nto defined for fuse {fuse.name}")
            otp_value = "0x" + fuse.get_bytes_value(raw=True).hex()
            ret += f"# Fuse {fuse.name}, index {fuse.otp_index} and value: {otp_value}.\n"
            ret += cls.get_fuse_write_cmd(fuse.otp_index, fuse.get_value(raw=True))
            ret += "\n\n"
        return ret

    @classmethod
    def get_fuse_write_cmd(
        cls, index: int, value: int, lock: bool = False, verify: bool = False
    ) -> str:
        """Get fuse write command."""
        ret = f"efuse-program-once {index} {f'0x{value:X}'}"
        ret = f"{ret} {'--verify' if verify else '--no-verify'}"
        if lock:
            ret = f"{ret} lock"
        return ret


class NxpeleFuseOperator(FuseOperator):
    """NXP ele fuse operator."""

    NAME = "nxpele"

    def __init__(self, ele_handler: Any):
        """Nxp ele fuse operator initialization."""
        from spsdk.ele.ele_comm import EleMessageHandler

        assert isinstance(ele_handler, EleMessageHandler)
        self.ele_handler = ele_handler

    def read_fuse(self, index: int) -> int:
        """Read a single fuse value.

        :param index: Index of a fuse
        :return: Fuse value
        """
        from spsdk.ele import ele_message

        read_common_fuse_msg = ele_message.EleMessageReadCommonFuse(index)
        with self.ele_handler:
            self.ele_handler.send_message(read_common_fuse_msg)
        return read_common_fuse_msg.fuse_value

    def write_fuse(self, index: int, value: int, lock: bool = False) -> None:
        """Write a single fuse.

        :param index: Index of a fuse
        :param value: Fuse value to be written
        :param lock: Lock fuse after write
        """
        from spsdk.ele import ele_message

        bit_position = index * 32
        bit_length = 32

        ele_fw_write_fuse_msg = ele_message.EleMessageWriteFuse(
            bit_position, bit_length, lock, value
        )
        with self.ele_handler:
            self.ele_handler.send_message(ele_fw_write_fuse_msg)

    @classmethod
    def get_fuse_script(
        cls, family: str, fuses: list[FuseRegister], revision: str = "latest"
    ) -> str:
        """Get fuse write command."""
        ret = (
            "# NXPELE fuses programming script\n"
            f"# Generated by SPSDK {spsdk_version}\n"
            f"# Chip: {family} rev:{revision}\n\n\n"
        )
        for fuse in fuses:
            if fuse.otp_index is None:
                raise SPSDKAttributeError(f"OTP index is nto defined for fuse {fuse.name}")
            otp_value = "0x" + fuse.get_bytes_value(raw=True).hex()
            ret += f"# Fuse {fuse.name}, index {fuse.otp_index} and value: {otp_value}.\n"
            ret += cls.get_fuse_write_cmd(fuse.otp_index, fuse.get_value(raw=True))
            ret += "\n\n"
        return ret

    @classmethod
    def get_fuse_write_cmd(
        cls, index: int, value: int, lock: bool = False, verify: bool = False
    ) -> str:
        """Get write command for a single fuse."""
        ret = f"write-fuse --index {index} --data {f'0x{value:X}'}"
        if verify:
            logger.debug("The 'verify' parameter is not applicable for nxpele command")
        if lock:
            ret = f"{ret} --lock"
        return ret


class Fuses:
    """Handle operations over fuses."""

    def __init__(
        self,
        family: str,
        revision: str = "latest",
        fuse_operator: Optional[FuseOperator] = None,
    ):
        """Fuses class to control fuses operations."""
        self.family = family
        self.revision = revision
        self.db = get_db(family, revision)
        if DatabaseManager.FUSES not in self.db.features:
            raise SPSDKError(f"The {self.family} has no fuses definition")
        self._operator = fuse_operator
        self.fuse_regs = self.get_init_regs(family, revision)
        # keep the context based on the latest operation: load_from_config/read_all etc.
        self.fuse_context: list[FuseRegister] = []

    @property
    def fuse_operator(self) -> FuseOperator:
        """Fuse operator property."""
        if self._operator is None:
            raise SPSDKError("Fuse operator is not defined.")
        return self._operator

    @fuse_operator.setter
    def fuse_operator(self, value: FuseOperator) -> None:
        """Fuse operator property setter."""
        if not isinstance(value, self.fuse_operator_type):
            raise SPSDKTypeError(
                f"Invalid fuse operator type: {type(value).__name__}. expected: {self.fuse_operator_type.__name__}"
            )

        self._operator = value

    @property
    def fuse_operator_type(self) -> Type[FuseOperator]:
        """Operator type based on family."""
        return self.get_fuse_operator_type(self.family, self.revision)

    @classmethod
    def get_fuse_operator_type(cls, family: str, revision: str = "latest") -> Type[FuseOperator]:
        """Get operator type based on family."""
        return FuseOperator.get_operator_type(
            get_db(family, revision).get_str(DatabaseManager.FUSES, "tool")
        )

    @classmethod
    def get_init_regs(cls, family: str, revision: str = "latest") -> FuseRegisters:
        """Get initialized fuse registers."""
        return FuseRegisters(family=family, revision=revision)

    def load_config(self, config: dict[str, Any]) -> None:
        """Loads the fuses configuration from dictionary.

        :param config: The configuration of fuses.
        """
        sch_full = self.get_validation_schemas(self.family, self.revision)
        check_config(config, sch_full)
        self.fuse_regs.load_yml_config(config["registers"])
        # set the fuse context to currently loaded registers
        self.fuse_context = [
            self.fuse_regs.find_reg(reg_name, include_group_regs=True)
            for reg_name in config["registers"].keys()
        ]

    @classmethod
    def load_from_config(cls, config: dict[str, Any]) -> Self:
        """Create fuses object from given configuration.

        :param config: The configuration of fuses.
        """
        sch_family = cls.get_validation_schemas_family()
        check_config(config, sch_family)
        fuses = cls(config["family"], config["revision"])
        fuses.load_config(config)
        return fuses

    def read_all(self) -> None:
        """Read all fuses from connected device."""
        ctx = []
        for reg in self.fuse_regs:
            try:
                self.read_single(reg.uid)
                ctx.append(reg)
            except SPSDKFuseOperationFailure as e:
                logger.warning(f"Unable to read the fuse {reg.name}: {str(e)}")
        self.fuse_context = ctx

    def read_single(self, name: str, check_locks: bool = True) -> int:
        """Read single fuse from device.

        :param name: Fuse name or uid.
        :param check_locks: Check value of lock fuse before reading
        """
        reg = self.fuse_regs.find_reg(name, include_group_regs=True)
        if not reg.access.is_readable:
            raise SPSDKFuseOperationFailure(
                f"Unable to read fuse {name}. Fuse access: {reg.access.description}"
            )
        lock_fuse = self.fuse_regs.get_lock_fuse(reg)
        if lock_fuse and check_locks:
            logger.debug("Reading the value of lock register first.")
            # if the fuse locks itself, do not read it
            self.read_single(lock_fuse.uid, check_locks=lock_fuse != reg)
            if FuseLock.READ_LOCK in reg.get_active_locks():
                raise SPSDKFuseOperationFailure(
                    f"Fuse {reg.name} read operation is locked by lock fuse {lock_fuse.name}."
                )

        if reg.has_group_registers():
            for sub_reg in reg.sub_regs:
                self.read_single(sub_reg.uid)
            self.fuse_context = [reg]
            return reg.get_value()
        if reg.otp_index is None:
            raise SPSDKFuseConfigurationError("OTP index is not defined")
        value = self.fuse_operator.read_fuse(reg.otp_index)
        reg.set_value(value)
        self.fuse_regs.update_locks()
        self.fuse_context = [reg]
        return value

    def write_multiple(self, names: list[str]) -> None:
        """Write multiple fuses to the device.

        :param names: List of fuse names or uids.
        """
        for name in names:
            reg = self.fuse_regs.find_reg(name, include_group_regs=True)
            self.write_single(reg.uid)

    def write_single(self, name: str, lock: bool = False) -> None:
        """Write single fuse to the device.

        :param name: Fuse name or uid.
        :param lock: Set lock after write.
        """

        def write_single_reg(reg: FuseRegister, lock: bool = False) -> None:
            if reg.otp_index is None:
                raise SPSDKError(f"OTP index for fuse {reg.name} is not set.")
            if not reg.access.is_writable:
                raise SPSDKFuseOperationFailure(
                    f"Unable to write fuse {name}. Fuse access: {reg.access.description}"
                )
            lock_reg = self.fuse_regs.get_lock_fuse(reg)
            if lock_reg:
                logger.debug("Reading the value of lock register first.")
                # if the fuse locks itself, do not check locks when reading
                self.read_single(lock_reg.uid, check_locks=lock_reg != reg)
                if FuseLock.WRITE_LOCK in reg.get_active_locks():
                    raise SPSDKFuseOperationFailure(
                        f"Fuse {reg.name} write operation is locked by lock fuse {lock_reg.name}."
                    )
            if reg.individual_write_lock in [
                IndividualWriteLock.ALWAYS,
                IndividualWriteLock.IMPLICIT,
            ]:
                reset = reg.get_reset_value()
                if self.read_single(reg.uid) != reset:
                    raise SPSDKFuseOperationFailure(
                        f"Fuse {reg.name} has non reset value {reset} and is write-locked."
                    )

            if lock and reg.individual_write_lock == IndividualWriteLock.IMPLICIT:
                logger.warning(
                    "The user's lock is ignored as the fuse will be implicitly locked after write"
                )
                lock = False
            if not lock and reg.individual_write_lock == IndividualWriteLock.ALWAYS:
                logger.info(
                    "Enabling the lock flag as the fuse has individual write lock set to 'always'"
                )
                lock = True
            self.fuse_operator.write_fuse(reg.otp_index, reg.get_value(), lock)
            # lock the local register so it matches the real state in chip
            if lock or reg.individual_write_lock == IndividualWriteLock.IMPLICIT:
                reg.lock(FuseLock.WRITE_LOCK)

        reg = self.fuse_regs.find_reg(name, include_group_regs=True)
        if reg.has_group_registers():
            for sub_reg in reg.sub_regs:
                write_single_reg(sub_reg, lock)
        else:
            write_single_reg(reg, lock)

    @staticmethod
    def get_supported_families() -> list[str]:
        """Return list of supported families."""
        return get_families(DatabaseManager.FUSES)

    @classmethod
    def get_validation_schemas_family(cls) -> list[dict[str, Any]]:
        """Get list of validation schemas for family key.

        :return: Validation list of schemas.
        """
        family_schema = get_schema_file("general")["family"]
        update_validation_schema_family(family_schema["properties"], cls.get_supported_families())
        return [family_schema]

    @classmethod
    def get_validation_schemas(cls, family: str, revision: str = "latest") -> list[dict[str, Any]]:
        """Create the validation schema.

        :param family: Family description.
        :param revision: Chip revision specification, as default, latest is used.
        :return: List of validation schemas.
        """
        sch_family: list[dict] = cls.get_validation_schemas_family()
        update_validation_schema_family(
            sch_family[0]["properties"], cls.get_supported_families(), family, revision
        )
        sch_cfg = get_schema_file(DatabaseManager.FUSES)
        init_regs = cls.get_init_regs(family, revision)
        sch_cfg["fuses"]["properties"]["registers"][
            "properties"
        ] = init_regs.get_validation_schema()["properties"]
        return sch_family + [sch_cfg["fuses"]]

    @classmethod
    def generate_config_template(cls, family: str, revision: str = "latest") -> str:
        """Generate fuses configuration template.

        :param family: Family for which the template should be generated.
        :param revision: Family revision of chip.
        """
        val_schemas = cls.get_validation_schemas(family, revision)
        return CommentedConfig(f"Fuses template for {family}.", val_schemas).get_template()

    def create_fuse_script(self) -> str:
        """The function creates the blhost/nxpele script to burn fuses.

        :return: Content of blhost/nxpele script file.
        """
        fuse_regs = []
        for reg in self.fuse_context:
            if reg.has_group_registers():
                for sub_reg in reg.sub_regs[:: -1 if reg.reverse_subregs_order else 1]:
                    fuse_regs.append(sub_reg)
            else:
                fuse_regs.append(reg)
        return self.fuse_operator_type.get_fuse_script(
            family=self.family, revision=self.revision, fuses=fuse_regs
        )

    def get_config(self, diff: bool = False) -> dict[str, Any]:
        """The function creates the configuration.

        :param diff: If set, only changed registers will be placed in configuration.
        """
        ret: dict[str, Any] = {"family": self.family, "revision": self.revision}
        ret["registers"] = self.fuse_regs.get_config(diff)
        logger.debug("The fuse configuration was created.")
        return ret


class FuseScript:
    """Class for generating scripts for writing fuses."""

    def __init__(
        self,
        family: str,
        revision: str,
        feature: str,
        index: Optional[int] = None,
        fuses_key: str = "fuses",
    ):
        """Initialize FuseScript object."""
        self.feature = feature
        self.family = family
        self.revision = revision

        self.db = get_db(family, revision)

        if DatabaseManager.FUSES not in self.db.features:
            raise SPSDKError(f"The {self.family} has no fuses definition")

        self.fuses = FuseRegisters(
            family=family,
            revision=revision,
            base_endianness=Endianness.LITTLE,
        )

        self.operator = FuseOperator.get_operator_type(
            self.db.get_str(DatabaseManager.FUSES, "tool", "blhost")
        )

        if index is not None:
            # if index is present append it to the fuses key,
            # like fuses_0, fuses_1, etc.
            fuses_key += f"_{index}"

        self.fuses_db = self.db.get_dict(feature, fuses_key)

        # No verify flag means that fuse won't be verified after write
        # It is needed for read protected OTP (blhost --no-verify)
        self.no_verify = self.fuses_db.get("_no_verify", False)
        self.name = self.fuses_db.get("_name", "Fuse Script")

    def generate_file_header(self) -> str:
        """Generate file header."""
        return (
            f"# {self.operator.NAME} {self.name} fuses programming script\n"
            f"# Generated by SPSDK {spsdk_version}\n"
            f"# Family: {self.family} Revision: {self.revision}"
        )

    @staticmethod
    def get_object_value(value: str, attributes_object: object) -> Any:
        """Return object value if attributes object has attribute with the value name."""
        if value.startswith("__"):
            value = value[2:]
            if hasattr(attributes_object, value):
                return getattr(attributes_object, value)
        raise SPSDKValueError(f"Fuses: Object does not contain {value}")

    def generate_script(self, attributes_object: object, info_only: bool = False) -> str:
        """Generate script for writing fuses.

        This method generates a script for writing fuses based on the provided attributes object.
        The script includes the file header and the commands for setting the fuse values.


        Special attributes:
        - __str_value: Value with double underscore represents attribute of the object.

        :param attributes_object: An object containing the attributes used to set the fuse values.
        :param info_only: If True, only the information about the fuses is generated.
        :return: The generated script for writing fuses.
        """
        script = self.generate_file_header() + "\n"
        info = ""

        for key, value in self.fuses_db.items():
            extra_info = ""
            if key.startswith("_"):  # Skip private attributes
                continue
            reg = self.fuses.get_reg(key)
            if isinstance(value, (int, bool)):  # RAW int value or boolean
                reg.set_value(value_to_int(value), raw=True)

            elif isinstance(value, dict):  # value contains bitfields
                for sub_key, sub_value in value.items():
                    bitfield = reg.get_bitfield(sub_key)
                    if isinstance(sub_value, (int, bool)):
                        bitfield.set_value(value_to_int(sub_value), raw=True)
                    elif isinstance(sub_value, str):
                        sub_value = self.get_object_value(sub_value, attributes_object)
                        if sub_value:
                            bitfield.set_value(sub_value)

                    extra_info += (
                        f"# Bitfield: {bitfield.name}"
                        + f", Description: {bitfield.description}"
                        + f", Value: {bitfield.get_hex_value()}\n"
                    )
            elif isinstance(value, str):  # Value from object
                value = self.get_object_value(value, attributes_object)
                if value:
                    reg.set_value(value)

            script += f"\n# Value: {hex(reg.get_value())}\n"
            script += f"# Description: {reg.description}\n"
            script += extra_info
            if extra_info:
                script += "# WARNING! Partially set register, check all bitfields before writing\n"
            if reg.sub_regs:
                script += f"# Grouped register name: {reg.name}\n\n"
                info += f"\n --== Grouped register name: {reg.name} ==-- \n"
                for reg in reg.sub_regs:
                    script += f"# OTP ID: {reg.name}, Value: {hex(reg.get_value())}\n"
                    if reg.otp_index is None:
                        raise SPSDKError(f"OTP index is not defined for {reg.name}")
                    script += (
                        self.operator.get_fuse_write_cmd(
                            reg.otp_index, reg.get_value(raw=True), verify=not self.no_verify
                        )
                        + "\n"
                    )
                    info += f"OTP ID: {reg.otp_index}, Value: {hex(reg.get_value(raw=True))}\n"
            else:
                script += f"# OTP ID: {reg.name}\n\n"
                if reg.otp_index is None:
                    raise SPSDKError(f"OTP index is not defined for {reg.name}")
                script += (
                    self.operator.get_fuse_write_cmd(
                        reg.otp_index, reg.get_value(raw=True), verify=not self.no_verify
                    )
                    + "\n"
                )
                info += f"OTP ID: {reg.otp_index}, Value: {hex(reg.get_value(raw=True))}\n"

        if info_only:
            return info
        return script

    def write_script(self, filename: str, output_dir: str, attributes_object: Any) -> str:
        """Write script to file.

        :return: The path to the generated script file.
        """
        script_content = self.generate_script(attributes_object)
        output = get_abs_path(f"{filename}_{self.operator.NAME}.bcf", output_dir)
        write_file(script_content, output)
        return output
