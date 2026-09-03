from cryptography.hazmat.primitives.asymmetric import ec

def partner_ephemeral_key():
    return ec.generate_private_key(ec.SECP256R1())
