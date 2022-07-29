#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2019-2022 NXP
#
# SPDX-License-Identifier: BSD-3-Clause

"""Base for SPSDK exceptions."""

#######################################################################
# # Secure Provisioning SDK Exceptions
#######################################################################


class SPSDKError(Exception):
    """Secure Provisioning SDK Base Exception."""

    fmt = "SPSDK: {description}"

    def __init__(self, desc: str = None) -> None:
        """Initialize the base SPSDK Exception."""
        super().__init__()
        self.description = desc

    def __str__(self) -> str:
        return self.fmt.format(description=self.description or "Unknown Error")


class SPSDKValueError(SPSDKError, ValueError):
    """SPSDK standard value error."""


class SPSDKIOError(SPSDKError, IOError):
    """SPSDK standard IO error."""


class SPSDKNotImplementedError(SPSDKError, NotImplementedError):
    """SPSDK standard not implemented error."""


class SPSDKLengthError(SPSDKError, ValueError):
    """SPSDK parsing error of any AHAB containers.

    Input/output data must be of at least container declared length bytes long.
    """


class SPSDKOverlapError(SPSDKError, ValueError):
    """Data overlap error."""


class SPSDKAlignmentError(SPSDKError, ValueError):
    """Data improperly aligned."""


class SPSDKParsingError(SPSDKError):
    """Cannot parse binary data."""
