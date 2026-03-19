import config
import db

db.inicializar_db()
for admin_id in config.ADMIN_IDS:
    db.activar_premium(admin_id)
    print(f"Premium activado para admin {admin_id}")
