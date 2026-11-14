from shared import transport
from domain import policy

def api():
    transport()
    transport()
    return policy()

def worker():
    return transport()

def callback(fn):
    return fn()
