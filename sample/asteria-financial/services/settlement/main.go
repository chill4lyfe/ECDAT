package settlement
import (
  "crypto/rand"
  "crypto/rsa"
)
func NewSigningKey() (*rsa.PrivateKey, error) { return rsa.GenerateKey(rand.Reader, 2048) }
