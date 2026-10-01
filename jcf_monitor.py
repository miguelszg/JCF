import re
import time
import requests

# ================== CONFIGURACIÓN ==================
JS_URL = "https://jovenesconstruyendoelfuturo.stps.gob.mx/focalizacion/dtmlp.js"

TG_TOKEN = "8820568216:AAGgPUnkHe8YP4tHoj3fuYJcSHRk0YgH93w"
TG_CHAT_ID = "8019676684"
INTERVAL = 60  # Consultar cada 30 segundos

# [22] monitorea solo Querétaro; pon [] si quieres monitorear todo el país
WATCH_STATES = [22]
# ===================================================

RE_CONSULTA = re.compile(
    r"ultima:\s*'([^']*)'.*?tipo_apertura:\s*'([^']*)'.*?cond_status:\s*'([^']*)'", re.S
)

RE_EDO = re.compile(
    r"idedo:\s*(\d+),\s*status:\s*(\d+),\s*lstatus:\s*'([^']*)',\s*edo:\s*'([^']*)',"
    r"\s*avance_edo:\s*'([^']*)'.*?estatus:\s*'([^']*)'", re.S
)

RE_MUN = re.compile(
    r"edo:\s*(\d+),\s*mun:\s*(\d+),\s*ledo:\s*'([^']*)',\s*lmun:\s*'([^']*)',"
    r"\s*status:\s*(\d+),\s*lstatus\s*:\s*'([^']*)',\s*avance_mun:\s*'([^']*)'", re.S
)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[ERROR Telegram] {e}")
        return False

def fetch_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    r = requests.get(JS_URL, headers=headers, timeout=15)
    r.raise_for_status()
    content = r.text

    m_cons = RE_CONSULTA.search(content)
    ultima = m_cons.group(1) if m_cons else "Desconocida"

    estados = {}
    for match in RE_EDO.finditer(content):
        idedo, status, lstatus, edo, avance_edo, estatus = match.groups()
        estados[int(idedo)] = {
            "nombre": edo,
            "status": int(status),
            "lstatus": lstatus,
            "estatus": estatus,
            "avance": avance_edo
        }

    municipios = []
    for match in RE_MUN.finditer(content):
        edo_id, mun_id, ledo, lmun, status, lstatus, avance_mun = match.groups()
        municipios.append({
            "edo_id": int(edo_id),
            "mun_id": int(mun_id),
            "ledo": ledo,
            "lmun": lmun,
            "status": int(status),
            "lstatus": lstatus,
            "avance": avance_mun
        })

    if not estados or not municipios:
        raise ValueError("No se pudieron extraer estados o municipios del JS")

    return ultima, estados, municipios

def main():
    print("Iniciando monitor de JCF...")
    
    try:
        ultima, estados, municipios = fetch_data()
        
        # Filtrar municipios a monitorear
        target_muns = [
            m for m in municipios 
            if not WATCH_STATES or m["edo_id"] in WATCH_STATES
        ]

        # 1. ENVIAR REPORTE INICIAL COMPLETO
        msg_inicio = f"🚀 <b>MONITOR JCF INICIADO</b>\n"
        msg_inicio += f"📅 <i>Actualizado al: {ultima}</i>\n\n"
        msg_inicio += "📋 <b>Estatus actual de municipios:</b>\n"

        abiertos_count = 0
        for m in target_muns:
            # Icono según disponibilidad (status != 0 es disponible)
            icon = "🟢" if m["status"] != 0 else "🔴"
            if m["status"] != 0:
                abiertos_count += 1
            msg_inicio += f"{icon} <b>{m['lmun']}</b> ({m['ledo']}): {m['lstatus']}\n"

        msg_inicio += f"\n📊 Total abiertos: <b>{abiertos_count}</b> / {len(target_muns)}"
        msg_inicio += "\n\n<i>El bot te notificará inmediatamente cuando algún municipio cambie de estatus.</i>"

        send_telegram(msg_inicio)
        print("Reporte inicial enviado a Telegram.")

        # Guardar estado actual de todos los municipios
        # Map: (edo_id, mun_id) -> status
        known_status = { (m["edo_id"], m["mun_id"]): m["status"] for m in target_muns }

    except Exception as e:
        print(f"Error en inicio: {e}")
        known_status = {}

    # 2. BUCLE DE MONITOREO CONTINUO
    while True:
        try:
            ultima, estados, municipios = fetch_data()
            print(f"[{time.strftime('%H:%M:%S')}] Revisando cambios... (Plataforma: {ultima})")

            target_muns = [
                m for m in municipios 
                if not WATCH_STATES or m["edo_id"] in WATCH_STATES
            ]

            changes = []
            for m in target_muns:
                key = (m["edo_id"], m["mun_id"])
                old_status = known_status.get(key)
                new_status = m["status"]

                # Si cambió el estatus en relación a la revisión anterior
                if old_status is not None and old_status != new_status:
                    changes.append((m, old_status, new_status))
                
                known_status[key] = new_status

            # Notificar si hubo cambios
            if changes:
                msg_cambio = "⚠️ <b>¡CAMBIO DE ESTATUS DETECTADO!</b>\n\n"
                for m, old_st, new_st in changes:
                    if new_st != 0:
                        msg_cambio += f"🎉 <b>¡APERTURA!</b>\n"
                    else:
                        msg_cambio += f"🔒 <b>CIERRE</b>\n"
                    
                    msg_cambio += f"📍 <b>{m['lmun']}, {m['ledo']}</b>\n"
                    msg_cambio += f"Nuevo estatus: <b>{m['lstatus']}</b>\n\n"

                msg_cambio += f"<i>Última actualización: {ultima}</i>"
                send_telegram(msg_cambio)
                print("¡Alerta de cambio enviada a Telegram!")

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()