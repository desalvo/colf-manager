from email.message import EmailMessage
import smtplib
import ssl


def send_smtp_message(settings, to_address, subject, body, attachments=None):
    host = (settings.get("host") or "").strip()
    from_email = (settings.get("from_email") or "").strip()
    if not host:
        raise ValueError("Server SMTP non configurato")
    if not from_email:
        raise ValueError("Mittente SMTP non configurato")
    if not to_address or "@" not in to_address:
        raise ValueError("Destinatario e-mail non valido")
    if not subject:
        raise ValueError("Oggetto obbligatorio")

    message = EmailMessage()
    from_name = (settings.get("from_name") or "colf-manager").strip()
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body or "Documento inviato tramite colf-manager.")

    for filename, mime_type, payload in attachments or []:
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)

    port = int(settings.get("port") or 587)
    security = settings.get("security") or "starttls"
    username = settings.get("username") or ""
    password = settings.get("password") or ""
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=20)
    try:
        client.ehlo()
        if security == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if username:
            client.login(username, password)
        client.send_message(message)
    finally:
        client.quit()
