"""Minimal native Security.framework generic-password adapter for Temper secrets."""

from __future__ import annotations

import ctypes
import platform
from ctypes import POINTER, byref, c_char_p, c_int32, c_long, c_uint8, c_void_p
from typing import Final, Protocol


class KeychainBackendError(ValueError):
    """Raised when Keychain cannot complete an exact same-user operation."""


class KeychainBackend(Protocol):
    def add(self, *, service: str, account: str, payload: bytes) -> None: ...

    def get(self, *, service: str, account: str) -> bytes | None: ...

    def update(self, *, service: str, account: str, payload: bytes) -> None: ...

    def delete(self, *, service: str, account: str) -> bool: ...


_ERR_SEC_SUCCESS: Final = 0
_ERR_SEC_DUPLICATE_ITEM: Final = -25299
_ERR_SEC_ITEM_NOT_FOUND: Final = -25300
_ERR_SEC_INTERACTION_NOT_ALLOWED: Final = -25308
_UTF8: Final = 0x08000100


class SecurityFrameworkKeychainBackend:
    """Store generic-password bytes through native Security.framework calls only."""

    _cf: ctypes.CDLL
    _security: ctypes.CDLL
    _k_sec_class: c_void_p
    _k_sec_class_generic_password: c_void_p
    _k_sec_attr_service: c_void_p
    _k_sec_attr_account: c_void_p
    _k_sec_value_data: c_void_p
    _k_sec_return_data: c_void_p
    _k_sec_match_limit: c_void_p
    _k_sec_match_limit_one: c_void_p
    _k_cf_boolean_true: c_void_p

    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise KeychainBackendError("macOS Keychain is unavailable on this platform")
        try:
            self._cf = ctypes.CDLL(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            self._security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        except OSError as error:
            raise KeychainBackendError("macOS Keychain frameworks are unavailable") from error
        self._configure_functions()
        self._k_sec_class = self._constant(self._security, "kSecClass")
        self._k_sec_class_generic_password = self._constant(
            self._security, "kSecClassGenericPassword"
        )
        self._k_sec_attr_service = self._constant(self._security, "kSecAttrService")
        self._k_sec_attr_account = self._constant(self._security, "kSecAttrAccount")
        self._k_sec_value_data = self._constant(self._security, "kSecValueData")
        self._k_sec_return_data = self._constant(self._security, "kSecReturnData")
        self._k_sec_match_limit = self._constant(self._security, "kSecMatchLimit")
        self._k_sec_match_limit_one = self._constant(self._security, "kSecMatchLimitOne")
        self._k_cf_boolean_true = self._constant(self._cf, "kCFBooleanTrue")

    @staticmethod
    def _constant(library: ctypes.CDLL, name: str) -> c_void_p:
        value = c_void_p.in_dll(library, name).value
        if value is None:
            raise KeychainBackendError(f"required Keychain constant {name} is unavailable")
        return c_void_p(value)

    def _configure_functions(self) -> None:
        self._cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_long]
        self._cf.CFStringCreateWithCString.restype = c_void_p
        self._cf.CFDataCreate.argtypes = [c_void_p, POINTER(c_uint8), c_long]
        self._cf.CFDataCreate.restype = c_void_p
        self._cf.CFDataGetLength.argtypes = [c_void_p]
        self._cf.CFDataGetLength.restype = c_long
        self._cf.CFDataGetBytePtr.argtypes = [c_void_p]
        self._cf.CFDataGetBytePtr.restype = POINTER(c_uint8)
        self._cf.CFDictionaryCreateMutable.argtypes = [c_void_p, c_long, c_void_p, c_void_p]
        self._cf.CFDictionaryCreateMutable.restype = c_void_p
        self._cf.CFDictionarySetValue.argtypes = [c_void_p, c_void_p, c_void_p]
        self._cf.CFDictionarySetValue.restype = None
        self._cf.CFRelease.argtypes = [c_void_p]
        self._cf.CFRelease.restype = None
        self._security.SecItemAdd.argtypes = [c_void_p, c_void_p]
        self._security.SecItemAdd.restype = c_int32
        self._security.SecItemCopyMatching.argtypes = [c_void_p, POINTER(c_void_p)]
        self._security.SecItemCopyMatching.restype = c_int32
        self._security.SecItemUpdate.argtypes = [c_void_p, c_void_p]
        self._security.SecItemUpdate.restype = c_int32
        self._security.SecItemDelete.argtypes = [c_void_p]
        self._security.SecItemDelete.restype = c_int32

    def add(self, *, service: str, account: str, payload: bytes) -> None:
        query, retained = self._base_query(service=service, account=account)
        data = self._data(payload)
        retained.append(data)
        self._cf.CFDictionarySetValue(query, self._k_sec_value_data, data)
        try:
            status = int(self._security.SecItemAdd(query, None))
            if status == _ERR_SEC_DUPLICATE_ITEM:
                raise KeychainBackendError("Keychain enrollment already exists")
            self._require_success(status)
        finally:
            self._release(query, retained)

    def get(self, *, service: str, account: str) -> bytes | None:
        query, retained = self._base_query(service=service, account=account)
        self._cf.CFDictionarySetValue(query, self._k_sec_return_data, self._k_cf_boolean_true)
        self._cf.CFDictionarySetValue(query, self._k_sec_match_limit, self._k_sec_match_limit_one)
        result = c_void_p()
        try:
            status = int(self._security.SecItemCopyMatching(query, byref(result)))
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                return None
            self._require_success(status)
            if not result.value:
                raise KeychainBackendError("Keychain returned an empty result reference")
            length = int(self._cf.CFDataGetLength(result))
            pointer = self._cf.CFDataGetBytePtr(result)
            if length < 0 or (length > 0 and not pointer):
                raise KeychainBackendError("Keychain returned invalid protected bytes")
            return bytes(pointer[index] for index in range(length))
        finally:
            if result.value:
                self._cf.CFRelease(result)
            self._release(query, retained)

    def update(self, *, service: str, account: str, payload: bytes) -> None:
        query, query_retained = self._base_query(service=service, account=account)
        attributes = self._dictionary()
        data = self._data(payload)
        self._cf.CFDictionarySetValue(attributes, self._k_sec_value_data, data)
        try:
            status = int(self._security.SecItemUpdate(query, attributes))
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                raise KeychainBackendError("Keychain enrollment is unavailable")
            self._require_success(status)
        finally:
            self._release(attributes, [data])
            self._release(query, query_retained)

    def delete(self, *, service: str, account: str) -> bool:
        query, retained = self._base_query(service=service, account=account)
        try:
            status = int(self._security.SecItemDelete(query))
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                return False
            self._require_success(status)
            return True
        finally:
            self._release(query, retained)

    def _base_query(self, *, service: str, account: str) -> tuple[c_void_p, list[c_void_p]]:
        query = self._dictionary()
        service_value = self._string(service)
        account_value = self._string(account)
        retained = [service_value, account_value]
        self._cf.CFDictionarySetValue(query, self._k_sec_class, self._k_sec_class_generic_password)
        self._cf.CFDictionarySetValue(query, self._k_sec_attr_service, service_value)
        self._cf.CFDictionarySetValue(query, self._k_sec_attr_account, account_value)
        return query, retained

    def _dictionary(self) -> c_void_p:
        value = self._cf.CFDictionaryCreateMutable(None, 0, None, None)
        if not value:
            raise KeychainBackendError("macOS could not allocate a Keychain request")
        return c_void_p(value)

    def _string(self, value: str) -> c_void_p:
        created = self._cf.CFStringCreateWithCString(None, value.encode("utf-8"), _UTF8)
        if not created:
            raise KeychainBackendError("macOS could not encode a Keychain identifier")
        return c_void_p(created)

    def _data(self, payload: bytes) -> c_void_p:
        array = (c_uint8 * len(payload)).from_buffer_copy(payload)
        created = self._cf.CFDataCreate(None, array, len(payload))
        if not created:
            raise KeychainBackendError("macOS could not encode protected bytes")
        return c_void_p(created)

    def _release(self, container: c_void_p, values: list[c_void_p]) -> None:
        for value in values:
            self._cf.CFRelease(value)
        self._cf.CFRelease(container)

    @staticmethod
    def _require_success(status: int) -> None:
        if status == _ERR_SEC_SUCCESS:
            return
        if status == _ERR_SEC_INTERACTION_NOT_ALLOWED:
            raise KeychainBackendError("macOS Keychain is locked or interaction is unavailable")
        raise KeychainBackendError(f"macOS Keychain refused the credential operation ({status})")
