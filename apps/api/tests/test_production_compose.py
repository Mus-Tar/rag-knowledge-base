from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker is required for Compose validation",
)
def test_production_compose_only_publishes_caddy_ports() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "compose.production.yaml",
            "--env-file",
            ".env.example",
            "config",
            "--format",
            "json",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(result.stdout)["services"]

    assert services["api"].get("ports", []) == []
    assert services["web"].get("ports", []) == []
    assert services["caddy"]["ports"] == [
        {"mode": "ingress", "protocol": "tcp", "published": "80", "target": 80},
        {"mode": "ingress", "protocol": "tcp", "published": "443", "target": 443},
    ]
    assert set(services["api"]["networks"]) == {"internal", "public"}
    assert "ollama" not in services


@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker is required for Compose validation",
)
def test_server_compose_binds_caddy_to_loopback() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "compose.production.yaml",
            "-f",
            "compose.server.yaml",
            "--env-file",
            ".env.example",
            "config",
            "--format",
            "json",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    caddy_ports = json.loads(result.stdout)["services"]["caddy"]["ports"]

    assert caddy_ports == [
        {
            "host_ip": "127.0.0.1",
            "mode": "ingress",
            "protocol": "tcp",
            "published": "9000",
            "target": 80,
        }
    ]
