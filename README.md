# NVR

Un enregistreur vidéo réseau (NVR) auto-hébergé : il ingère plusieurs flux
vidéo (caméras IP RTSP, caméra USB, flux HTTP/MJPEG), les enregistre en
continu sur un disque dur, et sert de passerelle pour les regarder en direct
ou en différé depuis un téléphone ou un ordinateur, via un navigateur web.

## Fonctionnalités

- **Plusieurs flux vidéo** : ajoutez, modifiez, activez/désactivez autant de
  caméras que votre machine peut en gérer, directement depuis l'interface web.
- **Enregistrement continu sur disque** : chaque caméra enregistre en
  fichiers de 10 minutes (configurable), avec purge automatique par ancienneté
  et par espace disque libre pour ne jamais saturer le disque.
- **Passerelle vidéo → téléphone / ordinateur** : lecture en direct (HLS,
  quelques secondes de latence, compatible navigateur mobile/desktop sans
  application) et relecture des enregistrements, avec téléchargement.
- **Redémarrage automatique** des flux en cas de coupure caméra ou réseau.
- **Authentification** simple par identifiant/mot de passe, session signée.

## Architecture en bref

```
Camera (RTSP/HTTP/USB) --ffmpeg--> enregistrement (fichiers .mp4 sur /data)
                        --ffmpeg--> direct (HLS) --HTTP--> navigateur (tel./PC)
```

Chaque caméra est gérée par deux processus `ffmpeg` indépendants et
supervisés (redémarrage automatique avec backoff en cas d'échec) : un pour
l'enregistrement, un pour le direct. La plupart des caméras IP acceptent
plusieurs connexions simultanées ; si la vôtre n'en accepte qu'une, utilisez
son "sous-flux" (résolution réduite) pour le direct via le champ *URL du
flux secondaire*.

Le backend est en Python (FastAPI). L'interface web est en HTML/JS simple
(pas de build), avec [hls.js](https://github.com/video-dev/hls.js) pour la
lecture du direct dans les navigateurs qui ne supportent pas HLS nativement
(Safari iOS le supporte nativement).

## Démarrage rapide (Docker, recommandé)

Prérequis : Docker et Docker Compose installés sur la machine reliée au
disque dur (un PC, un NAS, un Raspberry Pi...).

```bash
git clone <ce-depot>
cd NVR
cp .env.example .env
```

Éditez `.env` :
- `NVR_DISK_PATH` : le point de montage de votre disque dur (ex.
  `/mnt/disque-nvr`), c'est là que seront stockés les enregistrements.
- `NVR_ADMIN_PASSWORD` : changez le mot de passe par défaut.
- `NVR_SECRET_KEY` : générez-en une avec `openssl rand -hex 32`.

Puis lancez :

```bash
docker compose up -d --build
```

L'interface est alors disponible sur `http://<ip-de-la-machine>:8000`.

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

## Ajouter une caméra

Dans l'interface, cliquez sur **+ Camera** et renseignez :

- **Type de source** :
  - `RTSP` : la grande majorité des caméras IP. URL du type
    `rtsp://utilisateur:motdepasse@192.168.1.50:554/stream1` (consultez la
    documentation de votre caméra pour le chemin exact ; par exemple
    `/Streaming/Channels/101` pour beaucoup de caméras Hikvision/Dahua-like).
  - `HTTP / MJPEG` : flux HTTP MJPEG (`http://.../video`).
  - `USB` : caméra/webcam branchée en local, URL = chemin du périphérique,
    ex. `/dev/video0` (nécessite de passer le périphérique au conteneur, voir
    `docker-compose.yml`).
  - `Test` : mire synthétique, utile pour vérifier que tout fonctionne sans
    caméra réelle.
- **URL du flux secondaire (optionnel)** : si votre caméra propose un
  "sous-flux" basse résolution, indiquez-le ici pour le direct — cela réduit
  la charge CPU et la bande passante vers le téléphone, tout en gardant le
  flux principal en haute résolution pour l'enregistrement.

## Regarder depuis le téléphone

- **Sur le même réseau Wi-Fi** : ouvrez `http://<ip-locale-du-serveur>:8000`
  dans le navigateur du téléphone.
- **À distance (hors du domicile)** : n'exposez pas ce service directement
  sur Internet sans précaution. La façon la plus simple et la plus sûre est
  d'installer un VPN personnel comme [Tailscale](https://tailscale.com/) ou
  [WireGuard](https://www.wireguard.com/) sur le serveur et le téléphone : le
  téléphone accède alors au NVR comme s'il était sur le réseau local, sans
  ouvrir aucun port sur votre box internet. Si vous exposez malgré tout le
  service sur Internet, placez-le derrière un reverse proxy HTTPS (ex.
  Caddy, Nginx + Let's Encrypt) et gardez un mot de passe fort.

## Configuration (variables d'environnement)

| Variable | Défaut | Description |
|---|---|---|
| `NVR_DATA_DIR` | `data` | Dossier racine (enregistrements, config, HLS) |
| `NVR_ADMIN_USERNAME` | `admin` | Identifiant de connexion |
| `NVR_ADMIN_PASSWORD` | `changeme` | Mot de passe de connexion (**à changer**) |
| `NVR_SECRET_KEY` | *(généré et conservé automatiquement)* | Clé de signature des sessions |
| `NVR_SEGMENT_SECONDS` | `600` | Durée d'un fichier d'enregistrement (secondes) |
| `NVR_RETENTION_DAYS` | `14` | Suppression des enregistrements plus vieux que N jours |
| `NVR_MIN_FREE_DISK_PERCENT` | `10` | Purge des plus anciens enregistrements sous ce seuil d'espace libre |
| `NVR_HLS_SEGMENT_SECONDS` | `2` | Taille des segments HLS (latence du direct) |
| `NVR_PORT` | `8000` | Port d'écoute |

## Structure du dépôt

```
app/
  config.py          configuration (variables d'environnement)
  models.py           modèles de données (Camera, ...)
  store.py            persistance des caméras (YAML)
  ffmpeg_cmd.py        construction des commandes ffmpeg
  ffmpeg_manager.py    supervision des processus ffmpeg (démarrage/redémarrage)
  retention.py         purge automatique des enregistrements
  auth.py              authentification par session
  api/                 routes FastAPI (auth, caméras, médias, système)
  static/              interface web (HTML/CSS/JS, sans build)
tests/                 tests automatisés (pytest)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Un test de bout en bout (`tests/test_smoke_pipeline.py`) démarre un vrai
processus `ffmpeg` sur une source de test et vérifie que l'enregistrement et
le flux HLS sont bien produits sur disque ; il est automatiquement ignoré si
`ffmpeg` n'est pas installé.

## Dépannage

- **Une caméra reste en état "Erreur"** : vérifiez l'URL RTSP (identifiants,
  chemin), que la caméra est bien accessible depuis la machine du NVR
  (`ping`, port 554 ouvert), et que `NVR_DATA_DIR` est accessible en écriture.
  Les journaux du conteneur (`docker compose logs -f nvr`) affichent le
  dernier message d'erreur `ffmpeg`.
- **Disque plein** : le service purge automatiquement les enregistrements
  les plus anciens sous le seuil `NVR_MIN_FREE_DISK_PERCENT`. Réduisez
  `NVR_RETENTION_DAYS` si l'espace disque est limité par rapport au nombre de
  caméras.
- **Pas de son en direct** : c'est volontaire — le direct est envoyé en
  vidéo seule pour garantir la compatibilité avec tous les navigateurs et
  limiter la consommation de données mobiles. Les enregistrements
  téléchargés conservent le son d'origine de la caméra.
