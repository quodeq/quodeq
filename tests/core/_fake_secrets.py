"""Credential-shaped test values, assembled at runtime.

Built by concatenation so no complete token sits in the repository for a
secret scanner (ours, GitHub's, a pre-commit hook) to flag. None of them is a
real credential.
"""
from __future__ import annotations

AWS_KEY = "AKIA" + "Q3EXAMPLE7TESTKY"
GITHUB_TOKEN = "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
OPENAI_KEY = "sk" + "-proj-" + "Abc123Def456Ghi789Jkl012"
ANTHROPIC_KEY = "sk" + "-ant-" + "api03-Zyx987Wvu654Tsr321Qpo0"
PEM = (
    "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw\n"
    "7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u+qKhbwKfBstIs+bMY2Zkp18gnTxKLxoS2tFc\n"
    "-----END RSA " + "PRIVATE KEY-----"
)
GENERIC_VALUE = "q8Zr4" + "Lm2Vx9Tn6Wb3"
