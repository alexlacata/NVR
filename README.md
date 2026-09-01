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
- **Caméras PTZ** : pilotage pan/tilt/zoom et préréglages (presets) via
  ONVIF, directement depuis le téléphone.
- **Bande passante maîtrisée pour le direct** : bitrate et résolution du
  flux "direct" plafonnables indépendamment de l'enregistrement — pensé pour
  les liaisons 4G/5G limitées (routeur cellulaire type Peplink).
- **Ligne du temps et vignettes** : relecture par simple clic sur une ligne
  du temps 24h ou sur une bande de vignettes, générées à intervalle
  configurable à partir des enregistrements déjà sur le disque.

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

Le PTZ et la limite de bande passante du direct se configurent ensuite sur
la page de la caméra (section *Bande passante du direct* et *PTZ*).

## Piloter une caméra PTZ

Sur la page de la caméra, cochez **Camera PTZ (pilotage ONVIF)** et
renseignez :

- **URL du service ONVIF** : `http://<ip-camera>:<port>/onvif/device_service`
  (port ONVIF le plus souvent `80` ou `8080` — different du port RTSP `554` ;
  reportez-vous à la doc de votre caméra). Vérifiez au préalable que le
  service ONVIF est bien activé dans les réglages de la caméra.
- **Utilisateur / mot de passe ONVIF** : souvent les mêmes identifiants que
  pour le flux RTSP, mais pas toujours — certaines caméras ont un compte
  ONVIF séparé.

Une fois activé, un pavé directionnel et les boutons de zoom apparaissent
au-dessus de la liste des enregistrements : maintenez un bouton appuyé pour
déplacer la caméra, relâchez pour arrêter. Le bouton **+ Préselection**
enregistre la position actuelle de la caméra sous un nom, pour y revenir
d'un tap.

## Relire un enregistrement : ligne du temps et vignettes

Sur la page de la caméra, sous la vidéo, une ligne du temps représente les
24 heures de la date sélectionnée : les portions enregistrées apparaissent
en surbrillance. Cliquez n'importe où sur la ligne pour lancer la lecture à
cet instant précis — le serveur retrouve automatiquement le bon fichier et
se positionne au bon endroit dedans, vous n'avez pas besoin de chercher le
fichier vous-même.

En dessous, une bande de vignettes (miniatures) défile horizontalement ;
chacune est extraite des enregistrements déjà sur le disque, à intervalle
régulier. Cliquer sur une vignette lance la lecture à cet instant, comme sur
la ligne du temps. Réglez l'intervalle par caméra dans *Vignettes (ligne du
temps)* sur la page de la caméra (par défaut : une vignette par minute,
`NVR_THUMBNAIL_INTERVAL_SECONDS`). Comme pour les enregistrements, les
vignettes ne coûtent aucune bande passante caméra supplémentaire : elles
sont extraites localement des fichiers déjà enregistrés, jamais d'une
connexion en direct.

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

## Déploiement avec un routeur 4G (Peplink ou équivalent)

Cas d'usage typique : le NVR et les caméras sont sur site (chantier,
événement, véhicule...), reliés à Internet par un routeur cellulaire
(Peplink ou autre) qui fait office de liaison retour, et vous voulez
regarder/enregistrer à distance.

**Topologie recommandée : le NVR reste sur place, à côté des caméras.**
Le disque dur et les caméras restent en réseau local (Ethernet/Wi-Fi
local), seul le trafic de *visionnage* (HLS vers votre téléphone) traverse
la liaison 4G. C'est nettement plus économe en data et plus robuste qu'un
NVR distant qui devrait faire transiter en continu les flux RTSP des
caméras sur la 4G pour pouvoir enregistrer.

1. **Accès distant via le Peplink** : deux options, selon ce que propose
   votre modèle —
   - **SpeedFusion VPN / InControl Remote Web Access** (si disponible sur
     votre Peplink) : le plus simple, pas de port à ouvrir.
   - **Redirection de port (port forwarding)** sur le Peplink vers le port
     `8000` du NVR : fonctionne partout, mais exposez alors le service
     derrière HTTPS (reverse proxy) et gardez un mot de passe fort — voir
     la section *Regarder depuis le téléphone* ci-dessus. Une alternative
     plus sûre reste un VPN dédié (Tailscale/WireGuard) au-dessus de la
     liaison Peplink.
2. **Limitez la consommation de data** : sur chaque caméra, réglez
   *Bitrate maximum du direct* (ex. `500`-`800` kbps) et *Résolution du
   direct* (ex. `640x360`) dans les réglages de la caméra. L'enregistrement
   local, lui, reste toujours en pleine qualité — seul le flux envoyé vers
   votre téléphone est réduit. Un forfait 4G data-limité tient ainsi
   beaucoup mieux la charge, y compris avec plusieurs caméras.
3. **Fiabilité sur liaison cellulaire** : le flux RTSP est déjà transporté
   en TCP par défaut (plus tolérant aux pertes/latence que l'UDP sur une
   liaison mobile), et chaque flux redémarre automatiquement en cas de
   coupure (bascule Peplink entre SIM/WAN, perte de couverture...). Côté
   lecture, hls.js réessaie déjà automatiquement les segments manquants ;
   si les coupures sont fréquentes, augmentez `NVR_HLS_LIST_SIZE` pour
   donner plus de marge (fenêtre de rattrapage plus longue) au prix d'un
   direct légèrement moins "temps réel".

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
| `NVR_HLS_LIST_SIZE` | `6` | Nombre de segments HLS conservés dans la playlist (marge sur liaison instable) |
| `NVR_THUMBNAIL_INTERVAL_SECONDS` | `60` | Intervalle par défaut entre deux vignettes (secondes), surchargeable par caméra |
| `NVR_THUMBNAIL_CHECK_INTERVAL_SECONDS` | `30` | Fréquence de vérification des nouveaux enregistrements à traiter |
| `NVR_PORT` | `8000` | Port d'écoute |

## Structure du dépôt

```
app/
  config.py          configuration (variables d'environnement)
  models.py           modèles de données (Camera, ...)
  store.py            persistance des caméras (YAML)
  ffmpeg_cmd.py        construction des commandes ffmpeg
  ffmpeg_manager.py    supervision des processus ffmpeg (démarrage/redémarrage)
  retention.py         purge automatique des enregistrements et vignettes
  recordings.py         nommage/parcours des segments enregistrés (partagé)
  thumbnails.py          extraction des vignettes depuis les segments termines
  auth.py              authentification par session
  onvif_ptz.py          client ONVIF (pilotage PTZ)
  ptz_registry.py        cache des clients PTZ par caméra
  api/                 routes FastAPI (auth, caméras, médias, PTZ, système)
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
- **Le pavé PTZ ne répond pas / "Préselections indisponibles"** : vérifiez
  que le service ONVIF est activé dans les réglages de la caméra, que
  l'URL ONVIF est correcte (port souvent différent du port RTSP) et que les
  identifiants ONVIF sont les bons. Les commandes PTZ échouent silencieusement
  si la caméra ONVIF n'est pas joignable (le bouton ne fait rien) ; les
  journaux du serveur affichent le détail de l'erreur.
