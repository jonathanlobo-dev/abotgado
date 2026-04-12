"""
conftest.py — Configuración compartida para pytest.
Asegura encoding UTF-8 y sys.path correcto.
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
