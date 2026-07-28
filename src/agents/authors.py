# Registro dei nomi mostrati in chat per ciascun nodo. Chainlit associa in
# automatico l'avatar corrispondente in public/avatars/{nome}.* (case-insensitive),
# in base al nome esatto passato come author= a cl.Message - basta aggiungere
# la voce qui e il file .svg per dare un profilo a un nuovo nodo.


class Authors:
    SYSTEM = "System"
    INTAKE = "Anagrafica"
