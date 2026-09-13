from cryptography.hazmat.primitives.asymmetric import ec, ed25519

def issue_signing_keys():
    return ec.generate_private_key(ec.SECP256R1()), ed25519.Ed25519PrivateKey.generate()
