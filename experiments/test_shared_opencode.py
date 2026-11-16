"""Regression checks for the cross-task OpenCode donor (2026-11-14)."""

from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import shared_opencode as shared
from benchflow.agents import install
from benchflow.sandbox import env_layers as layers

RECORD = dict(image_id="sha256:" + "a" * 64, tag="skillcanvas-opencode:test",
              archive_sha256="b" * 64, files_sha256="c" * 64, links_sha256="d" * 64,
              arch="amd64", libc="glibc")


class SharedOpenCodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_installer_is_not_reinterpreted(self):
        plan = shared.native_plan()
        self.assertIsNone(shared.shared_recipe(replace(plan.recipe, install_cmd="custom"), RECORD))

    async def test_native_guards_and_configuration_remain(self):
        # Guards the donor adapter: the native generator still produces the
        # root environment, runtime-log mount check and USER restoration.
        recipe = shared.shared_recipe(shared.native_plan().recipe, RECORD)
        source = layers.agent_layer_dockerfile(recipe, "task-base", "e" * 64, user="agent")
        self.assertIn("USER root", source)
        self.assertTrue(source.endswith("USER agent\n"))
        self.assertIn("runtime log mount", source)
        self.assertNotIn("npm install", recipe.install_cmd)
        self.assertIn(RECORD["archive_sha256"], recipe.install_cmd)

    async def test_moved_donor_is_rejected_before_native_build(self):
        async def should_not_run(*args, **kwargs):
            self.fail("a changed donor reached a native build")
        with patch.object(layers.DockerLayers, "ensure_agent_layer", should_not_run), \
             patch.object(layers, "agent_layer_dockerfile"), \
             patch.object(install, "install_from_layer"):
            shared.install_adapter(RECORD)
            env = SimpleNamespace(_inspect=self.changed_image)
            base = SimpleNamespace(libc="glibc", arch="amd64")
            with self.assertRaises(layers.LayerError):
                await layers.DockerLayers.ensure_agent_layer(
                    env, shared.native_plan().recipe, "base", base=base)

    async def changed_image(self, ref):
        return {"Id": "sha256:changed"}

    async def test_incompatible_system_uses_original_recipe(self):
        observed = []
        async def original(env, recipe, base_ref, **kwargs):
            observed.append(recipe)
            return "original"
        with patch.object(layers.DockerLayers, "ensure_agent_layer", original), \
             patch.object(layers, "agent_layer_dockerfile"), \
             patch.object(install, "install_from_layer"):
            shared.install_adapter(RECORD)
            recipe = shared.native_plan().recipe
            base = SimpleNamespace(libc="musl", arch="amd64")
            self.assertEqual(await layers.DockerLayers.ensure_agent_layer(
                object(), recipe, "base", base=base), "original")
            self.assertEqual(observed, [recipe])

    async def test_runtime_corruption_never_falls_back_to_install(self):
        async def original_ensure(*args, **kwargs):
            return SimpleNamespace(key="shared-key")
        async def original_from(*args, **kwargs):
            self.fail("corrupted toolchain was admitted")
        async def inspect(ref):
            return {"Id": RECORD["image_id"]}
        async def exec_bad(*args, **kwargs):
            return SimpleNamespace(return_code=1)
        with patch.object(layers.DockerLayers, "ensure_agent_layer", original_ensure), \
             patch.object(layers, "agent_layer_dockerfile"), \
             patch.object(install, "install_from_layer", original_from):
            shared.install_adapter(RECORD)
            env = SimpleNamespace(_inspect=inspect, exec=exec_bad)
            base = SimpleNamespace(libc="glibc", arch="amd64")
            await layers.DockerLayers.ensure_agent_layer(
                env, shared.native_plan().recipe, "base", base=base)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RuntimeError):
                    await install.install_from_layer(env, shared.native_plan(), Path(directory),
                                                     layer_key="shared-key")


if __name__ == "__main__":
    unittest.main()
