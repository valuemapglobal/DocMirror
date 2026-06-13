# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Tests for Dependency Injection Container
"""

import pytest
from docmirror.di import (
    container,
    get_settings,
    get_cache,
    get_orchestrator,
    get_dispatcher,
    reset_container,
)
from docmirror.di.container import DocMirrorContainer


class TestDIContainer:
    """Test DI Container functionality."""
    
    def teardown_method(self):
        """Reset container after each test."""
        reset_container()
    
    def test_container_singleton(self):
        """Test container returns same instance."""
        c1 = container
        c2 = container
        assert c1 is c2
    
    def test_settings_singleton(self):
        """Test settings is singleton."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
    
    def test_cache_singleton(self):
        """Test cache is singleton."""
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2
    
    def test_dispatcher_singleton(self):
        """Test dispatcher is singleton."""
        d1 = get_dispatcher()
        d2 = get_dispatcher()
        assert d1 is d2
    
    def test_orchestrator_singleton(self):
        """Test orchestrator is singleton."""
        o1 = get_orchestrator()
        o2 = get_orchestrator()
        assert o1 is o2
    
    def test_reset_container(self):
        """Test container reset."""
        # Initialize
        settings = get_settings()
        dispatcher = get_dispatcher()
        
        # Reset
        reset_container()
        
        # Should create new instances
        new_settings = get_settings()
        new_dispatcher = get_dispatcher()
        
        assert settings is not new_settings
        assert dispatcher is not new_dispatcher
    
    def test_lazy_initialization(self):
        """Test lazy initialization."""
        c = DocMirrorContainer()
        
        # Should be None initially
        assert c._settings is None
        assert c._cache is None
        assert c._dispatcher is None
        
        # Access should initialize
        _ = c.settings
        assert c._settings is not None
    
    def test_settings_type(self):
        """Test settings type."""
        from docmirror.configs.settings import DocMirrorSettings
        
        settings = get_settings()
        assert isinstance(settings, DocMirrorSettings)
    
    def test_dispatcher_type(self):
        """Test dispatcher type."""
        from docmirror.framework.dispatcher import ParserDispatcher
        
        dispatcher = get_dispatcher()
        assert isinstance(dispatcher, ParserDispatcher)
    
    def test_orchestrator_type(self):
        """Test orchestrator type."""
        from docmirror.framework.orchestrator import Orchestrator
        
        orchestrator = get_orchestrator()
        assert isinstance(orchestrator, Orchestrator)
    
    def test_backward_compat_perception_factory(self):
        """Test backward compatibility with PerceptionFactory."""
        from docmirror.core.factory import PerceptionFactory
        
        # Should still work
        dispatcher = PerceptionFactory.get_dispatcher()
        assert dispatcher is not None
        
        # Reset should work
        PerceptionFactory.reset()
