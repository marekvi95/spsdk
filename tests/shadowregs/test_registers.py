#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2021 NXP
#
# SPDX-License-Identifier: BSD-3-Clause
""" Tests for registers utility."""

import os
import filecmp
import pytest

from spsdk.utils.registers import (BitfieldNotFound, EnumNotFound, RegConfig, Registers,
                                   RegsRegister,
                                   RegsBitField,
                                   RegsEnum,
                                   RegisterNotFound)

from spsdk.utils.misc import use_working_directory

TEST_DEVICE_NAME = "TestDevice1"
TEST_REG_NAME = "TestReg"
TEST_REG_OFFSET = 1024
TEST_REG_WIDTH = 32
TEST_REG_DESCR = "TestReg Description"
TEST_REG_REV = False
TEST_REG_ACCESS = "RW"
TEST_REG_VALUE = 0xA5A5A5A5

TEST_BITFIELD_NAME = "TestBitfiled"
TEST_BITFILED_OFFSET = 0x0F
TEST_BITFILED_WIDTH = 5
TEST_BITFIELD_RESET_VAL = 33
TEST_BITFIELD_ACCESS = "RW"
TEST_BITFIELD_DESCR = "Test Bitfield Description"
TEST_BITFIELD_SAVEVAL = 29
TEST_BITFIELD_OUTOFRANGEVAL = 70

TEST_ENUM_NAME = "TestEnum"
TEST_ENUM_VALUE_BIN = "0b10001"
TEST_ENUM_VALUE_HEX = "0x11"
TEST_ENUM_VALUE_STRINT = "017"
TEST_ENUM_VALUE_INT = 17
TEST_ENUM_VALUE_BYTES = b'\x11'
TEST_ENUM_RES_VAL = "0b010001"
TEST_ENUM_DESCR = "Test Enum Description"
TEST_ENUM_MAXWIDTH = 6

TEST_XML_FILE = "unit_test.xml"

def test_basic_regs(tmpdir):
    """Basic test of registers class."""
    regs = Registers(TEST_DEVICE_NAME)

    assert regs.dev_name == TEST_DEVICE_NAME

    reg1 = RegsRegister(TEST_REG_NAME, TEST_REG_OFFSET, TEST_REG_WIDTH, TEST_REG_DESCR, TEST_REG_REV, TEST_REG_ACCESS)

    with pytest.raises(RegisterNotFound):
        regs.find_reg("NonExisting")

    # Ther Registers MUST return empty erray
    assert regs.get_reg_names() == []

    with pytest.raises(TypeError):
        regs.remove_register("String")

    with pytest.raises(ValueError):
        regs.remove_register(reg1)

    # Now we could do tests with a register added to list
    regs.add_register(reg1)

    regs.remove_register_by_name(["String"])

    assert TEST_REG_NAME in regs.get_reg_names()

    regt = regs.find_reg(TEST_REG_NAME)

    assert regt == reg1

    with pytest.raises(TypeError):
        regs.add_register("Invalid Parameter")

    regt.set_value(TEST_REG_VALUE)
    assert reg1.get_value() == TEST_REG_VALUE.to_bytes(4,"big")

    filename = os.path.join(tmpdir, TEST_XML_FILE)
    regs.write_xml(filename)
    assert os.path.isfile(filename)

    printed_str = str(regs)

    assert TEST_DEVICE_NAME in printed_str
    assert TEST_REG_NAME in printed_str

    regs.remove_register_by_name([TEST_REG_NAME])

    with pytest.raises(RegisterNotFound):
        regs.find_reg(TEST_REG_NAME)
        assert False

def test_register():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    enum = RegsEnum(TEST_ENUM_NAME, 0, TEST_ENUM_DESCR)
    bitfield.add_enum(enum)

    parent_reg.add_bitfield(bitfield)

    printed_str = str(parent_reg)

    assert "Name:" in printed_str
    assert TEST_REG_NAME in printed_str
    assert TEST_REG_DESCR in printed_str
    assert "Width:" in printed_str
    assert "Access:" in printed_str
    assert "Bitfield" in printed_str
    assert TEST_BITFIELD_NAME in printed_str
    assert TEST_BITFIELD_DESCR in printed_str
    assert TEST_ENUM_NAME in printed_str
    assert TEST_ENUM_DESCR in printed_str

def test_register_invalid_val():
    reg = RegsRegister(TEST_REG_NAME,
                       TEST_REG_OFFSET,
                       TEST_REG_WIDTH,
                       TEST_REG_DESCR,
                       TEST_REG_REV,
                       TEST_REG_ACCESS)

    reg.set_value("Invalid")
    assert reg.get_value() == b''

    reg.set_value([1, 2])
    assert reg.get_value() == b''

def test_enum():
    enum = RegsEnum(TEST_ENUM_NAME, 0, TEST_ENUM_DESCR)

    printed_str = str(enum)

    assert "Name:" in printed_str
    assert "Value:" in printed_str
    assert "Description:" in printed_str
    assert TEST_ENUM_NAME in printed_str
    assert "0b0" in printed_str
    assert TEST_ENUM_DESCR in printed_str

def test_enum_bin():
    enum = RegsEnum(TEST_ENUM_NAME, TEST_ENUM_VALUE_BIN, TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
    printed_str = str(enum)
    assert TEST_ENUM_RES_VAL in printed_str

def test_enum_hex():
    enum = RegsEnum(TEST_ENUM_NAME, TEST_ENUM_VALUE_HEX, TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
    printed_str = str(enum)
    assert TEST_ENUM_RES_VAL in printed_str

def test_enum_strint():
    enum = RegsEnum(TEST_ENUM_NAME, TEST_ENUM_VALUE_STRINT, TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
    printed_str = str(enum)
    assert TEST_ENUM_RES_VAL in printed_str

def test_enum_int():
    enum = RegsEnum(TEST_ENUM_NAME, TEST_ENUM_VALUE_INT, TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
    printed_str = str(enum)
    assert TEST_ENUM_RES_VAL in printed_str

def test_enum_bytes():
    enum = RegsEnum(TEST_ENUM_NAME, TEST_ENUM_VALUE_BYTES, TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
    printed_str = str(enum)
    assert TEST_ENUM_RES_VAL in printed_str

def test_enum_invalidval():
    try:
        enum = RegsEnum(TEST_ENUM_NAME, "InvalidValue", TEST_ENUM_DESCR, TEST_ENUM_MAXWIDTH)
        printed_str = str(enum)
        assert "N/A" in printed_str
    except TypeError:
        assert 0

def test_bitfield():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    enum = RegsEnum(TEST_ENUM_NAME, 0, TEST_ENUM_DESCR)
    bitfield.add_enum(enum)

    parent_reg.add_bitfield(bitfield)

    printed_str = str(bitfield)

    assert "Name:" in printed_str
    assert "Offset:" in printed_str
    assert "Width:" in printed_str
    assert "Access:" in printed_str
    assert "Reset val:" in printed_str
    assert "Description:" in printed_str
    assert "Enum" in printed_str

def test_bitfield_find():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    enum = RegsEnum(TEST_ENUM_NAME, 0, TEST_ENUM_DESCR)
    bitfield.add_enum(enum)

    parent_reg.add_bitfield(bitfield)

    assert bitfield == parent_reg.find_bitfield(TEST_BITFIELD_NAME)

    with pytest.raises(BitfieldNotFound):
        parent_reg.find_bitfield("Invalid Name")

def test_bitfield_has_enums():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    parent_reg.add_bitfield(bitfield)

    assert bitfield.has_enums() is False
    enum = RegsEnum(TEST_ENUM_NAME, 0, TEST_ENUM_DESCR)
    bitfield.add_enum(enum)

    assert bitfield.has_enums() is True

    assert enum in bitfield.get_enums()

def test_bitfield_value():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    bitfield.set_value(TEST_BITFIELD_SAVEVAL)
    assert bitfield.get_value() == TEST_BITFIELD_SAVEVAL

    with pytest.raises(ValueError):
        bitfield.set_value(TEST_BITFIELD_OUTOFRANGEVAL)

def test_bitfield_enums():
    parent_reg = RegsRegister(TEST_REG_NAME,
                              TEST_REG_OFFSET,
                              TEST_REG_WIDTH,
                              TEST_REG_DESCR,
                              TEST_REG_REV,
                              TEST_REG_ACCESS)

    bitfield = RegsBitField(parent_reg,
                            TEST_BITFIELD_NAME,
                            TEST_BITFILED_OFFSET,
                            TEST_BITFILED_WIDTH,
                            TEST_BITFIELD_DESCR,
                            TEST_BITFIELD_RESET_VAL,
                            TEST_BITFIELD_ACCESS)

    parent_reg.add_bitfield(bitfield)

    enums = []
    for n in range((1 << TEST_BITFILED_WIDTH)-1):
        enum = RegsEnum(f"{TEST_ENUM_NAME}{n}", n, f"{TEST_ENUM_DESCR}{n}", TEST_BITFILED_WIDTH)
        enums.append(enum)
        bitfield.add_enum(enum)

    enum_names = bitfield.get_enum_names()

    for n in range((1 << TEST_BITFILED_WIDTH)-1):
        assert n == bitfield.get_enum_constant(f"{TEST_ENUM_NAME}{n}")
        assert enums[n].name in enum_names

    for n in range((1 << TEST_BITFILED_WIDTH)):
        bitfield.set_value(n)
        if n < (1 << TEST_BITFILED_WIDTH)-1:
            assert f"{TEST_ENUM_NAME}{n}" == bitfield.get_enum_value()
        else:
            assert n == bitfield.get_enum_value()

    for n in range((1 << TEST_BITFILED_WIDTH)-1):
        bitfield.set_enum_value(f"{TEST_ENUM_NAME}{n}")
        assert n == bitfield.get_value()

    with pytest.raises(EnumNotFound):
        bitfield.get_enum_constant("Invalid name")

    regs = Registers(TEST_DEVICE_NAME)

    regs.add_register(parent_reg)

def test_registers_xml(data_dir, tmpdir):
    regs = Registers(TEST_DEVICE_NAME)

    with use_working_directory(data_dir):
        regs.load_registers_from_xml("registers.xml")

    with use_working_directory(tmpdir):
        regs.write_xml("registers.xml")

    regs2 = Registers(TEST_DEVICE_NAME)

    with use_working_directory(tmpdir):
        regs2.load_registers_from_xml("registers.xml")

    assert str(regs) == str(regs2)

def test_registers_corrupted_xml(data_dir, tmpdir):
    regs = Registers(TEST_DEVICE_NAME)

    with use_working_directory(data_dir):
        regs.load_registers_from_xml("registers_corr.xml")

    with use_working_directory(tmpdir):
        regs.write_xml("registers_corr.xml")

    assert not filecmp.cmp(os.path.join(data_dir, "registers_corr.xml"), os.path.join(tmpdir, "registers_corr.xml"))

    regs.clear()

    with use_working_directory(tmpdir):
        regs.load_registers_from_xml("registers_corr.xml")
        regs.write_xml("registers_corr1.xml")

    assert filecmp.cmp(os.path.join(tmpdir, "registers_corr.xml"), os.path.join(tmpdir, "registers_corr1.xml"))

    # Without clear - Cannot add register with same name as is already added
    with use_working_directory(tmpdir):
        regs.load_registers_from_xml("registers_corr.xml")
        regs.write_xml("registers_corr1.xml")

    assert filecmp.cmp(os.path.join(tmpdir, "registers_corr.xml"), os.path.join(tmpdir, "registers_corr1.xml"))

def test_reg_config_get_devices(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))
    devices = reg_config.get_devices()

    assert "test_device1" in devices
    assert "test_device2" in devices

def test_reg_config_get_devices_class(data_dir):
    devices = RegConfig.devices(os.path.join(data_dir, "reg_config.json"))

    assert "test_device1" in devices
    assert "test_device2" in devices

def test_reg_config_get_latest_revision(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    rev = reg_config.get_latest_revision("test_device1")
    assert rev == "x1"

    rev = reg_config.get_latest_revision("test_device2")
    assert rev == "b0"

def test_reg_config_get_revisions(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    revs = reg_config.get_revisions("test_device1")
    assert "x0" in revs
    assert "x1" in revs

    revs = reg_config.get_revisions("test_device2")
    assert "b0" in revs

def test_reg_config_get_address(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    addr = reg_config.get_address("test_device1")
    assert addr == "0xA5A5_1234"

    addr = reg_config.get_address("test_device2", remove_underscore=True)
    assert addr == "0x40000000"

def test_reg_config_get_data_file(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    data_file = reg_config.get_data_file("test_device1", "x0")
    assert os.path.join(data_dir, "test_device1_x0.xml") == data_file

    data_file = reg_config.get_data_file("test_device1", "x1")
    assert os.path.join(data_dir, "test_device1_x1.xml") == data_file

    data_file = reg_config.get_data_file("test_device2", "b0")
    assert os.path.join(data_dir, "test_device2_b0.xml") == data_file

def test_reg_config_get_antipoleregs(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    antipole = reg_config.get_antipole_regs("test_device1")
    assert antipole["INVERTED_REG"] == "INVERTED_REG_AP"

    antipole = reg_config.get_antipole_regs("test_device2")
    assert antipole["INVERTED_REG"] == "INVERTED_REG_AP"

def test_reg_config_get_computed_fields(data_dir):
    reg_config = RegConfig(os.path.join(data_dir, "reg_config.json"))

    computed_fields = reg_config.get_computed_fields("test_device1")
    assert computed_fields["COMPUTED_REG"]["TEST_FIELD1"] == "computed_reg_test_field1"
    assert computed_fields["COMPUTED_REG"]["TEST_FIELD2"] == "computed_reg_test_field2"
    assert computed_fields["COMPUTED_REG2"]["TEST_FIELD1"] == "computed_reg2_test_field1"
    assert computed_fields["COMPUTED_REG2"]["TEST_FIELD2"] == "computed_reg2_test_field2"

