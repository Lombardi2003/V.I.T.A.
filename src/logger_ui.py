import chainlit as cl
import asyncio

async def ui_print(text):
    """Sostituto del print() che scrive sia su Terminale che su Chainlit"""
    # 1. Scrive sul terminale vero (quello nero)
    print(text) 
    
    # Invia un messaggio a Chainlit
    try:
        await cl.Message(content=f"📝 `{text}`").send()
    except Exception:
        pass # Se non siamo in Chainlit, non fare nulla