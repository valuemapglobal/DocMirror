# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Tests for Dependency Injection Container
"""

import pytest

from docmirror.framework.di import (
    container,
    get_dispatcher,
    get_orchestrator,
    get_settings,
    reset_container,
)
from docmirror.framework.di.container import DocMirrorContainer


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
        settings = get_settings()
        dispatcher = get_dispatcher()
        orchestrator = get_orchestrator()

        reset_container()

        assert get_settings() is not settings
        assert get_dispatcher() is not dispatcher
        assert get_orchestrator() is not orchestrator

    def test_lazy_initialization(self):
        """Test lazy initialization."""
        c = DocMirrorContainer()

        assert c._settings is None
        assert c._dispatcher is None
        assert c._orchestrator is None

        _ = c.settings
        assert c._settings is not None

    def test_settings_type(self):
        """Test settings type."""
        from docmirror.configs.runtime.settings import DocMirrorSettings

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

    def test_perception_factory_shares_dispatcher(self):
        """PerceptionFactory must delegate to the same dispatcher singleton."""
        from docmirror.input.entry.factory import PerceptionFactory

        assert PerceptionFactory.get_dispatcher() is get_dispatcher()

        PerceptionFactory.reset()
        assert PerceptionFactory.get_dispatcher() is get_dispatcher()
