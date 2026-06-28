# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Tests for Result Pattern
"""

import pytest
from docmirror.errors.result import (
    Success,
    Failure,
    DocMirrorError,
    ErrorSeverity,
    FileTooLargeError,
    CacheError,
    success,
    failure,
    try_catch,
    try_catch_async,
)


class TestResultSuccess:
    """Test Success result type."""
    
    def test_create_success(self):
        """Test creating success result."""
        result = Success(42)
        assert result.is_success
        assert not result.is_failure
        assert result.value == 42
    
    def test_map_success(self):
        """Test mapping success value."""
        result = Success(10)
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_success
        assert mapped.value == 20
    
    def test_and_then_success(self):
        """Test chaining with and_then."""
        def divide(x):
            if x == 0:
                return Failure(DocMirrorError("Div by zero", "DIV_ZERO"))
            return Success(100 / x)
        
        result = Success(10).and_then(divide)
        assert result.is_success
        assert result.value == 10.0
    
    def test_or_else_success(self):
        """Test or_else on success returns self."""
        result = Success(42)
        fallback = result.or_else(lambda: Success(0))
        assert fallback.value == 42
    
    def test_get_or_raise_success(self):
        """Test get_or_raise on success."""
        result = Success(42)
        assert result.get_or_raise() == 42
    
    def test_get_or_default_success(self):
        """Test get_or_default on success."""
        result = Success(42)
        assert result.get_or_default(0) == 42


class TestResultFailure:
    """Test Failure result type."""
    
    def test_create_failure(self):
        """Test creating failure result."""
        error = DocMirrorError("Test error", "TEST")
        result = Failure(error)
        assert result.is_failure
        assert not result.is_success
        assert result.error == error
    
    def test_map_failure(self):
        """Test mapping failure returns self."""
        error = DocMirrorError("Test", "TEST")
        result = Failure(error)
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_failure
        assert mapped.error == error
    
    def test_and_then_failure(self):
        """Test and_then on failure returns self."""
        error = DocMirrorError("Test", "TEST")
        result = Failure(error)
        chained = result.and_then(lambda x: Success(x))
        assert chained.is_failure
    
    def test_or_else_failure(self):
        """Test or_else on failure executes fallback."""
        error = DocMirrorError("Test", "TEST")
        result = Failure(error)
        fallback = result.or_else(lambda: Success(42))
        assert fallback.is_success
        assert fallback.value == 42
    
    def test_get_or_raise_failure(self):
        """Test get_or_raise on failure raises error."""
        error = DocMirrorError("Test error", "TEST")
        result = Failure(error)
        with pytest.raises(DocMirrorError) as exc_info:
            result.get_or_raise()
        assert exc_info.value == error
    
    def test_get_or_default_failure(self):
        """Test get_or_default on failure returns default."""
        error = DocMirrorError("Test", "TEST")
        result = Failure(error)
        assert result.get_or_default(42) == 42


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_success_helper(self):
        """Test success helper."""
        result = success(42)
        assert isinstance(result, Success)
        assert result.value == 42
    
    def test_failure_helper(self):
        """Test failure helper."""
        error = DocMirrorError("Test", "TEST")
        result = failure(error)
        assert isinstance(result, Failure)
        assert result.error == error
    
    def test_try_catch_success(self):
        """Test try_catch with successful function."""
        result = try_catch(lambda: 42)
        assert result.is_success
        assert result.value == 42
    
    def test_try_catch_failure(self):
        """Test try_catch with failing function."""
        def failing_fn():
            raise ValueError("Test error")
        
        result = try_catch(failing_fn)
        assert result.is_failure
        assert "Test error" in result.error.message
    
    def test_try_catch_custom_error(self):
        """Test try_catch with custom error factory."""
        def failing_fn():
            raise ValueError("Test error")
        
        def error_factory(e):
            return CacheError(str(e))
        
        result = try_catch(failing_fn, error_factory)
        assert result.is_failure
        assert isinstance(result.error, CacheError)
    
    @pytest.mark.asyncio
    async def test_try_catch_async_success(self):
        """Test async try_catch with successful function."""
        async def async_fn():
            return 42
        
        result = await try_catch_async(async_fn)
        assert result.is_success
        assert result.value == 42
    
    @pytest.mark.asyncio
    async def test_try_catch_async_failure(self):
        """Test async try_catch with failing function."""
        async def async_fn():
            raise ValueError("Async error")
        
        result = await try_catch_async(async_fn)
        assert result.is_failure
        assert "Async error" in result.error.message


class TestErrorTypes:
    """Test specific error types."""
    
    def test_file_too_large_error(self):
        """Test FileTooLargeError."""
        error = FileTooLargeError(1024 * 1024 * 600, 1024 * 1024 * 500)
        assert error.code == "FILE_TOO_LARGE"
        assert error.severity == ErrorSeverity.FATAL
        assert not error.recoverable
        assert "600.0MB" in str(error)
    
    def test_cache_error(self):
        """Test CacheError."""
        error = CacheError("Redis unavailable")
        assert error.code == "CACHE_ERROR"
        assert error.severity == ErrorSeverity.RECOVERABLE
        assert error.recoverable
    
    def test_error_string_representation(self):
        """Test error string representation."""
        error = DocMirrorError("Test message", "TEST_CODE")
        assert str(error) == "[TEST_CODE] Test message"
        assert "TEST_CODE" in repr(error)


class TestResultIntegration:
    """Test Result pattern integration scenarios."""
    
    def test_chaining_operations(self):
        """Test chaining multiple operations."""
        def parse_int(x):
            try:
                return Success(int(x))
            except ValueError as e:
                return Failure(DocMirrorError(str(e), "PARSE_ERROR"))
        
        def double(x):
            return Success(x * 2)
        
        def to_string(x):
            return Success(str(x))
        
        result = (
            Success("42")
            .and_then(parse_int)
            .and_then(double)
            .and_then(to_string)
        )
        
        assert result.is_success
        assert result.value == "84"
    
    def test_error_propagation(self):
        """Test error propagation through chain."""
        def parse_int(x):
            try:
                return Success(int(x))
            except ValueError as e:
                return Failure(DocMirrorError(str(e), "PARSE_ERROR"))
        
        result = (
            Success("not_a_number")
            .and_then(parse_int)
            .map(lambda x: x * 2)
        )
        
        assert result.is_failure
        assert result.error.code == "PARSE_ERROR"
    
    def test_fallback_chain(self):
        """Test fallback chain."""
        def try_cache():
            return Failure(CacheError("Cache miss"))
        
        def try_database():
            return Failure(DocMirrorError("DB error", "DB_ERROR"))
        
        def use_default():
            return Success("default_value")
        
        result = (
            try_cache()
            .or_else(try_database)
            .or_else(use_default)
        )
        
        assert result.is_success
        assert result.value == "default_value"
    
    def test_recoverable_error_handling(self):
        """Test handling recoverable errors."""
        result = try_catch(
            lambda: 1 / 0,
            lambda e: CacheError(str(e))
        )
        
        if result.is_success:
            value = result.value
        elif result.error.recoverable:
            value = "fallback"
        else:
            raise result.error
        
        assert value == "fallback"
