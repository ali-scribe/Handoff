"""Handoff evaluation infrastructure.

A small, reproducible evaluation utility that runs a manually labeled dataset of
realistic handoff requests through the REAL Handoff analysis pipeline (AI
extraction + deterministic validation) and reports quality metrics.

This package is evaluation-only. It adds no runtime behavior to the product and
must never be imported by the application at startup.
"""
