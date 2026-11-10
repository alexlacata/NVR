# NVR

Un enregistreur vidéo réseau (NVR) auto-hébergé : il ingère plusieurs flux
vidéo (RTSP, RTMP, SRT, HTTP/MJPEG, caméra USB) de n'importe quelle marque
compatible ONVIF (Hikvision, Uniview, Dahua, Axis, Reolink, Amcrest,
Annke, EZVIZ, Foscam, TP-Link Tapo, Vivotek, Wyze, Lorex, Swann, Night Owl,
LTS/Loryta, Hanwha/Wisenet, Bosch, Panasonic, Geovision, Ubiquiti UniFi
Protect, et tout NVR/DVR générique compatible RTSP, ...), les
enregistre en continu sur un disque dur, et sert de passerelle pour les
regarder en direct ou en différé depuis un téléphone ou un ordinateur, via
un navigateur web.

## Fonctionnalités

- **Plusieurs flux vidéo** : ajoutez, modifiez, activez/désactivez autant de
  caméras que votre machine peut en gérer, directement depuis l'interface web.
- **Enregistrement continu sur disque** : chaque caméra enregistre en
  fichiers de 10 minutes (configurable), avec purge automatique par ancienneté
  et par espace disque libre pour ne jamais saturer le disque.
- **Surveillance de la machine** : en plus de l'espace disque, le tableau de
  bord affiche l'utilisation CPU, la RAM et la température du processeur
  (utile sur Raspberry Pi, qui peut chauffer et ralentir sans avertissement) —
  chaque indicateur passe en orange puis en rouge au-delà d'un seuil, et
  disparaît simplement s'il n'est pas lisible sur la machine (ex. dans un
  conteneur sans accès au capteur de température).
- **Passerelle vidéo → téléphone / ordinateur** : lecture en direct (HLS,
  quelques secondes de latence, compatible navigateur mobile/desktop sans
  application) et relecture des enregistrements, avec téléchargement.
- **Redémarrage automatique** des flux en cas de coupure caméra ou réseau.
- **Comptes utilisateurs** avec rôles administrateur/lecteur, session signée,
  et gestion des comptes et des réglages serveur directement depuis l'UI.
- **Interface mobile/PC fluide** : web app installable sur l'écran d'accueil
  (iOS/Android) pour un usage plein écran sans barre d'adresse, et un QR
  code dans les Paramètres pour ouvrir l'interface sur un téléphone sans
  taper l'adresse du serveur.
- **Caméras PTZ** : pilotage pan/tilt/zoom et préréglages (presets) via
  ONVIF, directement depuis le téléphone.
- **Bande passante maîtrisée pour le direct** : bitrate et résolution du
  flux "direct" plafonnables indépendamment de l'enregistrement — pensé pour
  les liaisons 4G/5G limitées (routeur cellulaire type Peplink).
- **Ligne du temps et vignettes** : relecture par simple clic sur une ligne
  du temps 24h ou sur une bande de vignettes, générées à intervalle
  configurable à partir des enregistrements déjà sur le disque.
- **Multi-protocole et multi-marque** : RTSP, RTMP, SRT, HTTP/MJPEG, USB.
  Détection automatique du flux via ONVIF (Hikvision, Uniview, Dahua, Axis,
  Reolink et toute caméra compatible), avec recherche sur le réseau local ou
  assistant de configuration par marque en secours (Hikvision, Uniview,
  Dahua, Axis, Reolink, Amcrest, Annke, EZVIZ, Foscam, TP-Link Tapo,
  Vivotek, Wyze, Lorex, Swann, Night Owl, LTS/Loryta, Hanwha/Wisenet,
  Bosch, Panasonic, Geovision, Ubiquiti UniFi Protect, ou un profil
  générique pour les NVR/DVR sans marque reconnue).

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

> **Recherche de caméras sur le réseau (WS-Discovery) en Docker** : le
> réseau `bridge` par défaut ne transmet pas le trafic multicast utilisé
> pour découvrir les caméras ONVIF automatiquement. Pour que le bouton
> **Rechercher sur le réseau** fonctionne, décommentez `network_mode: host`
> dans `docker-compose.yml` (Linux uniquement). Ce n'est pas nécessaire pour
> le reste de l'application, ni pour la détection ONVIF quand vous
> connaissez déjà l'adresse IP de la caméra.

Pas de Docker, ou installation sur Raspberry Pi ? Voir
[docs/installation.md](docs/installation.md).

## Documentation

Le reste de la documentation est rangé par thème dans `docs/` :

- **[Installation](docs/installation.md)** — sans Docker (systemd), déploiement
  sur Raspberry Pi (image prête à flasher, encodage matériel), variables
  d'environnement.
- **[Caméras](docs/cameras.md)** — ajouter une caméra, pilotage PTZ, relecture
  (ligne du temps et vignettes), programmation horaire, détection de
  mouvement et zones de masquage.
- **[Administration](docs/administration.md)** — notifications (webhook/e-mail),
  sauvegarde vers un second emplacement, journal d'activité, comptes
  utilisateurs et paramètres serveur.
- **[Accès réseau](docs/network-access.md)** — HTTPS, usage depuis le
  téléphone, annuaire multi-boîtiers ("Mes systèmes"), déploiement derrière
  un routeur 4G/5G.
- **[Développement](docs/development.md)** — structure du dépôt, mise à
  jour et retour en arrière, robustesse et limites connues, tests,
  dépannage.
