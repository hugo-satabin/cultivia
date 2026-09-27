import ngrok

def connect_ngrok():
    forwarder = ngrok.forward("localhost:8085", authtoken_from_env=True, domain="crayon-charm-marlin.ngrok-free.dev")
    print(f"Available at: {forwarder.url()}")

connect_ngrok()