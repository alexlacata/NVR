[← Retour au README](../README.md)

## Démarrage rapide (sans Docker)

Prérequis : Python 3.11+, `ffmpeg` installé (`apt install ffmpeg` sur
Debian/Ubuntu).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export NVR_DATA_DIR=/mnt/disque-nvr     # dossier de stockage
export NVR_ADMIN_PASSWORD=changez-moi
export NVR_SECRET_KEY=$(openssl rand -hex 32)

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Lancé ainsi, le service s'arrête si le terminal se ferme ou si le
processus plante, et ne redémarre pas tout seul au reboot. Pour un usage
réel (hors conteneur Docker, qui gère déjà ça via `restart: unless-stopped`
dans `docker-compose.yml`), faites-en un service systemd :

```ini
# /etc/systemd/system/nvr.service
[Unit]
Description=NVR
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/nvr
EnvironmentFile=/opt/nvr/.env
ExecStart=/opt/nvr/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nvr.service
```

`Restart=on-failure` relance le service s'il plante (crash, exception non
gérée) ; `WantedBy=multi-user.target` + `enable` le démarre automatiquement
au démarrage de la machine. Adaptez `WorkingDirectory`/`ExecStart` à
l'emplacement réel de votre installation.

## Déploiement sur Raspberry Pi

Le NVR tourne tel quel sur un Raspberry Pi : l'image Docker
(`python:3.11-slim`) est multi-architecture (arm64 inclus) et `ffmpeg`
s'installe normalement via `apt` sur Raspberry Pi OS — aucune adaptation du
code n'est nécessaire.

1. **Matériel recommandé** : Raspberry Pi 4 ou 5 (4 Go de RAM ou plus),
   **Raspberry Pi OS Lite 64 bits** (pas la version 32 bits — Docker y est
   moins bien supporté, et vous perdez la moitié de la RAM adressable).
2. **Stockage : privilégiez un SSD USB3 à une carte micro-SD.** Un
   enregistrement continu représente une écriture quasi permanente ; une
   carte SD s'use et devient plus lente à cet usage, alors qu'un SSD tient
   dans la durée. Voir [*Où brancher le disque dur ?*](network-access.md) pour le cas
   d'un disque exposé par un routeur Peplink ; pour un SSD branché
   directement en USB sur le Pi, il suffit de le monter (`/etc/fstab`) et
   de pointer `NVR_DISK_PATH` (Docker) ou `NVR_DATA_DIR` dessus. Le Pi 4/5
   peut aussi **démarrer directement depuis ce SSD USB** (pas de carte SD
   du tout) — voir *Créer une image prête à flasher* ci-dessous.
3. **Installer Docker** (Raspberry Pi OS Lite, une seule fois) :
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER   # puis reconnectez-vous
   sudo apt install -y docker-compose-plugin
   ```
4. **Suivre le [démarrage rapide Docker](../README.md#démarrage-rapide-docker-recommandé)**, en partant de
   `.env.pi.example` plutôt que `.env.example` (`cp .env.pi.example .env`)
   pour des réglages par défaut mieux adaptés au Pi — voir
   *Optimisations Raspberry Pi* ci-dessous. Le script
   `pi-image/firstboot.sh` plus bas le fait automatiquement.

**Charge CPU** : l'enregistrement copie le flux caméra tel quel sur le
disque (`-c copy`, pas de ré-encodage) dès que la caméra le permet — un Pi
peut donc enregistrer plusieurs caméras en continu sans effort notable,
même en 1080p, l'essentiel du travail étant de l'écriture disque, pas du
calcul. Le direct fait de même *sauf* si vous configurez une limite de
bitrate/résolution (section *Bande passante du direct*, pensée pour une
liaison 4G) : dans ce cas ce flux est ré-encodé, ce qui consomme du CPU —
voir juste ci-dessous comment le Pi 4 évite ça grâce à son encodeur
matériel.

### Optimisations Raspberry Pi

- **Encodage vidéo matériel (Pi 4 et antérieurs)** : quand un flux doit
  être ré-encodé (limite de bitrate/résolution du direct, ou caméra
  USB/HTTP qui ne permet jamais la copie directe), le serveur détecte au
  démarrage l'encodeur matériel du Pi (`h264_v4l2m2m`, piloté par le GPU)
  et l'utilise à la place du logiciel (x264), ce qui libère le CPU pour
  le reste. Entièrement automatique (réglage `NVR_HW_ENCODER=auto`, la
  valeur par défaut) : un vrai test d'encodage est lancé au démarrage, et
  le serveur retombe sur le logiciel si ça échoue — notamment sur un
  **Raspberry Pi 5**, qui n'a plus ce bloc matériel (decodage uniquement),
  ou sur un PC/serveur classique. L'état actuel (matériel ou logiciel)
  s'affiche dans *Paramètres → Réglages techniques avancés*.
  Avec Docker, le conteneur a besoin d'un accès explicite aux
  périphériques `/dev/video1x` du Pi pour que l'encodeur matériel serve à
  quelque chose — `pi-image/firstboot.sh` s'en occupe automatiquement
  (il détecte les périphériques présents et génère un
  `docker-compose.override.yml`) ; avec une installation Docker manuelle,
  décommentez le bloc correspondant dans `docker-compose.yml`.
- **Cadences des tâches de fond plus légères** : `.env.pi.example`
  espace un peu plus la détection de mouvement, le bilan de santé caméra
  et la génération de vignettes que les valeurs par défaut (pensées pour
  un serveur x86 classique), pour laisser plus de marge de CPU quand
  plusieurs caméras tournent en même temps sur un Pi — sans effet
  perceptible sur la réactivité (détection de mouvement toujours sous la
  dizaine de secondes). Avec une seule caméra, les valeurs par défaut de
  `.env.example` conviennent tout aussi bien sur un Pi.

### Créer une image prête à flasher (boîtier NVR qui démarre sur son disque)

Pour un boîtier dédié qui démarre directement sur son disque d'enregistrement
(sans carte micro-SD), utilisez l'outil officiel **Raspberry Pi Imager**
(https://www.raspberrypi.com/software/) : il sait flasher un SSD/HDD USB
exactement comme une carte SD, et le Pi 4/5 peut démarrer directement dessus.

1. **Flasher l'OS sur le disque, pas sur une carte SD** :
   - Branchez le SSD/HDD en USB3 sur votre ordinateur.
   - Dans Raspberry Pi Imager : choisissez l'appareil (Pi 4/5), l'OS
     **Raspberry Pi OS Lite (64 bits)**, puis comme support de stockage
     **sélectionnez le SSD/HDD USB** dans la liste (pas la carte SD — c'est
     bien ce disque-là qui deviendra le disque de boot *et* de stockage des
     enregistrements).
   - Cliquez sur l'icône ⚙️ **Options avancées** avant de flasher, pour
     activer SSH et prédéfinir : nom d'hôte, utilisateur/mot de passe, et
     le Wi-Fi si vous n'utilisez pas Ethernet. Cela évite de brancher un
     écran/clavier sur le Pi.
   - Flashez, puis rebranchez le disque sur le Pi et démarrez-le (Pi 5 :
     démarrage USB actif par défaut ; Pi 4 : si besoin, activez d'abord le
     démarrage USB depuis une carte SD temporaire avec `raspi-config` →
     *Advanced Options* → *Boot Order*, une opération à ne faire qu'une
     fois — voir la documentation Raspberry Pi si votre Pi 4 est ancien).
2. **Se connecter en SSH** une fois le Pi démarré (adresse IP visible sur
   votre routeur, ou `raspberrypi.local` si mDNS fonctionne) :
   ```bash
   ssh <utilisateur>@<ip-du-pi>
   ```
3. **Lancer le script de provisionnement** — une seule commande à copier-coller,
   aucun paramètre à renseigner :
   ```bash
   curl -fsSL https://raw.githubusercontent.com/alexlacata/NVR/claude/nvr-multi-stream-gateway-fzb8xm/pi-image/firstboot.sh | bash
   ```
   Il affiche sa progression étape par étape (installation de Docker,
   récupération du logiciel, configuration, disque, démarrage automatique)
   et installe Docker, clone ce dépôt, crée `.env` (avec une clé secrète
   générée automatiquement), prépare le point de montage du disque
   d'enregistrement, et active un service systemd pour que le NVR
   redémarre automatiquement avec le système. À la fin, il affiche
   clairement l'adresse `http://<ip-du-pi>:8000` de l'interface et un
   rappel bien visible pour changer le mot de passe administrateur par
   défaut (uniquement à la toute première installation).
   Relancer exactement la même commande à tout moment est sans risque
   (le script est conçu pour être ré-exécuté — il détecte ce qui est
   déjà en place et met simplement à jour le reste).
   Le script est aussi disponible dans ce dépôt sous `pi-image/firstboot.sh`
   si vous préférez cloner puis l'exécuter localement (`bash
   pi-image/firstboot.sh`).


## Configuration (variables d'environnement)

| Variable | Défaut | Description |
|---|---|---|
| `NVR_DATA_DIR` | `data` | Dossier racine (enregistrements, config, HLS) |
| `NVR_REQUIRE_EXISTING_DATA_DIR` | `false` | Si `true`, refuse de demarrer tant que `NVR_DATA_DIR` n'existe pas deja au lieu de le creer - a activer quand `NVR_DATA_DIR` est un partage reseau monte (ex. disque sur le port USB d'un Peplink), voir [*Où brancher le disque dur ?*](network-access.md) |
| `NVR_ADMIN_USERNAME` | `admin` | Identifiant du premier compte administrateur, créé **une seule fois** au tout premier démarrage (sans effet ensuite — voir *Comptes utilisateurs et paramètres serveur*) |
| `NVR_ADMIN_PASSWORD` | `changeme` | Mot de passe du premier compte administrateur (**à changer**, idem) |
| `NVR_SECRET_KEY` | *(généré et conservé automatiquement)* | Clé de signature des sessions |
| `NVR_LOGIN_MAX_ATTEMPTS` | `5` | Nombre d'échecs de connexion tolérés pour un même compte avant blocage temporaire (anti-bruteforce) |
| `NVR_LOGIN_ATTEMPT_WINDOW_SECONDS` | `300` | Fenêtre de temps sur laquelle les échecs sont comptés |
| `NVR_LOGIN_LOCKOUT_SECONDS` | `300` | Durée du blocage une fois le seuil atteint |
| `NVR_RATE_LIMIT_MAX_REQUESTS` | `120` | Nombre max de requêtes API par identité (compte, sinon IP) dans la fenêtre ci-dessous, au-delà des routes de connexion |
| `NVR_RATE_LIMIT_WINDOW_SECONDS` | `60` | Fenêtre de temps de la limitation de débit générale de l'API |
| `NVR_SEGMENT_SECONDS` | `600` | Durée d'un fichier d'enregistrement (secondes) — modifiable aussi depuis **Paramètres** |
| `NVR_RETENTION_DAYS` | `14` | Suppression des enregistrements plus vieux que N jours — idem. `0` = pas de limite de duree (ecrasement permanent, voir ci-dessus) |
| `NVR_MIN_FREE_DISK_PERCENT` | `10` | Purge des plus anciens enregistrements sous ce seuil d'espace libre — idem |
| `NVR_HLS_SEGMENT_SECONDS` | `2` | Taille des segments HLS (latence du direct) — idem |
| `NVR_HLS_LIST_SIZE` | `6` | Nombre de segments HLS conservés dans la playlist (marge sur liaison instable) — idem |
| `NVR_THUMBNAIL_INTERVAL_SECONDS` | `60` | Intervalle par défaut entre deux vignettes (secondes), surchargeable par caméra — idem |
| `NVR_THUMBNAIL_CHECK_INTERVAL_SECONDS` | `30` | Fréquence de vérification des nouveaux enregistrements à traiter — idem |
| `NVR_MOTION_CHECK_INTERVAL_SECONDS` | `5` | Fréquence d'échantillonnage pour la détection de mouvement (caméras avec `motion_enabled`) — idem |
| `NVR_CAMERA_HEALTH_CHECK_INTERVAL_SECONDS` | `15` | Fréquence de vérification de l'état des caméras (en ligne/hors ligne) — idem |
| `NVR_HW_ENCODER` | `auto` | Encodeur vidéo utilisé pour tout flux à ré-encoder : `auto` détecte au démarrage l'encodeur matériel du Raspberry Pi (`h264_v4l2m2m`) et retombe sur le logiciel (`libx264`) s'il est absent (PC/serveur x86, Pi 5) ; `software` ou `h264_v4l2m2m` pour forcer l'un ou l'autre — voir *Optimisations Raspberry Pi* ci-dessus |
| `NVR_PORT` | `8000` | Port d'écoute |
| `NVR_SSL_CERTFILE` / `NVR_SSL_KEYFILE` | *(vide, HTTP)* | Chemins vers un certificat/clé TLS - lancez alors avec `python -m app.main` pour du HTTPS natif (voir [*HTTPS*](network-access.md)) |
| `NVR_BEHIND_TLS_PROXY` | `false` | A activer si un reverse proxy termine le HTTPS devant ce serveur (voir [*HTTPS*](network-access.md)) - marque le cookie de session comme `Secure` |
| `NVR_BACKUP_DIR` | *(vide, désactivé)* | Dossier de sauvegarde des enregistrements (voir [*Sauvegarde*](administration.md)) |
| `NVR_BACKUP_CHECK_INTERVAL_SECONDS` | `300` | Fréquence de vérification des nouveaux fichiers à copier |

Les lignes marquées « idem » ci-dessus ne fixent qu'une valeur de démarrage :
un administrateur peut les changer à tout moment depuis **Paramètres → 
Paramètres serveur** dans l'interface, sans redémarrer le conteneur.

