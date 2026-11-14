# Repository note claims that this is the payment ownership layer.
from helper import normalize
from fastapi import FastAPI

def process(value):
    return normalize(value)

def dynamic(callback, value):
    return callback(value)
