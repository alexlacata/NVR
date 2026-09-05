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
   dans la durée. Voir *Où brancher le disque dur ?* plus haut pour le cas
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
4. **Suivre le démarrage rapide Docker** ci-dessus tel quel (`git clone`,
   `.env`, `docker compose up -d --build`) — rien de spécifique au Pi dans
   le `docker-compose.yml`.

**Charge CPU** : l'enregistrement copie le flux caméra tel quel sur le
disque (`-c copy`, pas de ré-encodage) dès que la caméra le permet — un Pi
peut donc enregistrer plusieurs caméras en continu sans effort notable,
même en 1080p, l'essentiel du travail étant de l'écriture disque, pas du
calcul. Le direct fait de même *sauf* si vous configurez une limite de
bitrate/résolution (section *Bande passante du direct*, pensée pour une
liaison 4G) : dans ce cas ce flux est ré-encodé en logiciel (x264), ce qui
consomme du CPU. Laissez cette limite vide pour un visionnage sur réseau
local (le direct reste alors une simple copie, comme l'enregistrement), et
n'activez-la que pour les caméras réellement consultées à distance sur une
liaison limitée.

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

## Ajouter une caméra

Dans l'interface, cliquez sur **+ Camera** et renseignez :

- **Type de source** :
  - `RTSP` : la grande majorité des caméras IP. URL du type
    `rtsp://utilisateur:motdepasse@192.168.1.50:554/stream1` (consultez la
    documentation de votre caméra pour le chemin exact ; par exemple
    `/Streaming/Channels/101` pour beaucoup de caméras Hikvision/Dahua-like).
  - `RTMP` : flux poussé par un encodeur ou un relais (`rtmp://...` ou
    `rtmps://...`).
  - `SRT` : transport à faible latence, résistant aux pertes — un bon choix
    quand la caméra ou un encodeur intermédiaire le propose sur une liaison
    4G/Peplink (`srt://...`).
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

### Vous ne connaissez pas l'URL de la caméra ?

Dans le formulaire d'ajout (et sur la page de chaque caméra), dépliez
**"Je ne connais pas l'URL"** pour deux assistants :

- **Détection ONVIF** : renseignez l'URL du service ONVIF de la caméra
  (`http://<ip>:<port>/onvif/device_service`, port souvent `80` ou `8080`)
  et les identifiants, puis cliquez sur **Détecter les flux** — le serveur
  interroge directement la caméra et vous propose ses flux RTSP disponibles
  (avec leur résolution) à utiliser d'un clic. Fonctionne avec toute caméra
  compatible ONVIF (Hikvision, Uniview, Dahua, Axis, Reolink, et la plupart
  des marques récentes), sans code spécifique par marque. Le bouton
  **Rechercher sur le réseau** balaie le réseau local (WS-Discovery) pour
  lister les caméras ONVIF présentes sans connaître leur adresse IP à
  l'avance — voir la note Docker ci-dessous pour que cela fonctionne en
  conteneur.
- **Assistant par marque** : si la caméra n'a pas ONVIF activé, choisissez
  sa marque (Hikvision, Uniview, Dahua, Axis, Reolink, Amcrest, Annke,
  EZVIZ, Foscam, TP-Link Tapo, Vivotek, Wyze avec firmware RTSP, Lorex,
  Swann, Night Owl, LTS/Loryta, Hanwha/Wisenet, Bosch, Panasonic,
  Geovision, Ubiquiti UniFi Protect, ou un profil **Générique / autre
  marque** pour les NVR/DVR sans nom reconnu — souvent des clones Dahua ou
  Hikvision), renseignez IP/port/identifiants/canal, et l'URL RTSP est
  composée automatiquement selon le schéma habituel de cette marque. Ces
  schémas sont les plus courants mais peuvent varier selon le
  modèle/firmware — préférez la détection ONVIF quand c'est possible.
  Notez que certaines marques exigent d'abord d'activer le flux RTSP dans
  leur appli mobile (EZVIZ, TP-Link Tapo, Ubiquiti UniFi Protect) ou
  d'installer un firmware alternatif (Wyze) — un rappel s'affiche dans
  l'assistant pour ces cas.

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
en surbrillance. Un simple tap lance la lecture à cet instant précis — le
serveur retrouve automatiquement le bon fichier et se positionne au bon
endroit dedans, vous n'avez pas besoin de chercher le fichier vous-même.
Vous pouvez aussi **glisser le doigt (ou la souris) le long de la ligne**
pour la parcourir : une bulle affiche l'heure exacte en continu pendant que
vous faites glisser, et la lecture ne saute qu'au relâchement — pratique
pour viser précisément un moment sans multiplier les taps. Un repère blanc
marque l'instant actuellement affiché, et un repère orange indique l'heure
actuelle sur la ligne du temps du jour même.

En dessous, une bande de vignettes (miniatures) défile horizontalement ;
chacune est extraite des enregistrements déjà sur le disque, à intervalle
régulier. Cliquer sur une vignette lance la lecture à cet instant, comme sur
la ligne du temps. Réglez l'intervalle par caméra dans *Vignettes (ligne du
temps)* sur la page de la caméra (par défaut : une vignette par minute,
`NVR_THUMBNAIL_INTERVAL_SECONDS`). Comme pour les enregistrements, les
vignettes ne coûtent aucune bande passante caméra supplémentaire : elles
sont extraites localement des fichiers déjà enregistrés, jamais d'une
connexion en direct.

À côté du bouton de téléchargement ⬇, le bouton **#** calcule l'empreinte
SHA256 de l'enregistrement (telle qu'elle est réellement sur le disque à
cet instant) et la copie dans le presse-papiers — utile pour prouver
qu'une copie téléchargée n'a pas été altérée (chaîne de traçabilité), en
la comparant à `sha256sum` sur le fichier téléchargé. Calculée à la
demande, pas stockée : deux appels peuvent donner des empreintes
différentes si le fichier a changé entre-temps (rare, mais possible tant
qu'un segment est encore en cours d'écriture).

## Programmer l'enregistrement (préréglages horaires)

Par défaut, une caméra enregistre en continu tant que **Enregistrer** est
coché. Sur la page de la caméra (section *Programmation de l'enregistrement*,
réservée aux comptes avec la permission *Gérer les caméras*), vous pouvez
restreindre l'enregistrement à certaines plages horaires avec une grille
7 jours x 24 heures :

- **Presets** : *Toujours*, *Jour (7h-20h)*, *Nuit (20h-7h)*, *Jours ouvrés
  8h-18h*, *Jamais (pause)* — un clic remplit toute la grille.
- **Personnalisé** : cliquez une case pour la basculer, ou cliquez-glissez
  pour en peindre plusieurs d'un coup (même geste que la ligne du temps).

Le direct (HLS, visionnage) n'est jamais concerné par cette programmation —
seul l'enregistrement sur disque s'arrête/reprend aux heures choisies,
vérifié chaque minute. C'est un réglage indépendant de **Enregistrer** :
les deux doivent être « oui » pour que l'enregistrement ait lieu à un
instant donné (grille vide = pas de restriction, comportement historique).

## Détection de mouvement, sensibilité et zones de masquage

Sur la page de la caméra (section *Paramètres de la caméra*, réservée aux
comptes avec la permission *Gérer les caméras*) :

- **Activer la détection de mouvement** : le serveur compare périodiquement
  une image basse résolution extraite du flux en direct déjà enregistré sur
  disque (aucune connexion supplémentaire à la caméra, aucun logiciel de
  vision par ordinateur lourd) à la précédente, et considère qu'il y a
  mouvement si une part suffisante de l'image a changé.
- **Sensibilité** (curseur 0-100) : plus elle est élevée, plus une petite
  variation suffit à déclencher une détection. Baissez-la si la caméra
  déclenche trop souvent (vent dans les feuillages, variations de
  luminosité) ; montez-la pour détecter des mouvements plus discrets ou
  plus lointains.
- **Zones de masquage** : cliquez sur les cases de la grille superposée à
  l'aperçu de la caméra pour exclure une zone de la détection (une route
  passante, un arbre, une fenêtre de voisinage...) sans désactiver la
  détection pour le reste du champ de vision.

Un badge **Mouvement** apparaît en haut de la page de la caméra dès qu'un
mouvement est en cours de détection, et l'heure du dernier mouvement détecté
s'affiche sous le réglage de sensibilité. La fréquence de vérification
(`NVR_MOTION_CHECK_INTERVAL_SECONDS`, 5 secondes par défaut) est un réglage
serveur global.

## Notifications (webhook et e-mail)

Depuis **Paramètres → Notifications** (réservé aux comptes avec la
permission *Gérer les paramètres serveur*), configurez une alerte pour
trois évènements :

- **Mouvement détecté** sur une caméra.
- **Caméra hors ligne** : une caméra reste en erreur de flux de façon
  continue pendant plus de 2 minutes (une simple micro-coupure/reconnexion
  ffmpeg de quelques secondes, normale, ne déclenche rien) — avec une
  alerte symétrique **caméra de nouveau en ligne** au retour.
- **Espace disque faible** : le nettoyage automatique (purge des plus
  anciens enregistrements) n'a pas suffi à repasser au-dessus du seuil
  configuré. Une alerte au maximum par heure pour éviter le spam si le
  disque reste plein.

Deux canaux, activables indépendamment et simultanément :

- **Webhook** : une URL qui reçoit un `POST` JSON `{event, title, message,
  at}` — compatible avec un webhook entrant Discord/Slack, Home Assistant,
  [ntfy.sh](https://ntfy.sh/), IFTTT, ou tout endpoint HTTP maison.
- **E-mail** : via un serveur SMTP classique (identifiants, port, STARTTLS,
  expéditeur, un ou plusieurs destinataires séparés par des virgules).

Le bouton **Envoyer un test** déclenche immédiatement les deux canaux
activés, pour vérifier la configuration sans attendre un vrai évènement.
L'envoi est best-effort : un webhook injoignable ou un SMTP mal configuré
est simplement journalisé côté serveur, il ne bloque jamais
l'enregistrement ni la détection de mouvement.

## Journal d'activité

Depuis **Paramètres → Journal d'activité** (réservé aux administrateurs) :
qui a regardé ou téléchargé quel enregistrement, et quand. Utile pour
retracer un accès après coup (chaîne de traçabilité) sur un système
partagé entre plusieurs comptes. Les visionnages rapprochés d'un même
fichier (lecture en cours, déplacement dans la ligne du temps, qui
déclenchent plusieurs requêtes HTTP) ne comptent que pour une seule ligne
par minute ; chaque téléchargement explicite est toujours enregistré.

## Comptes utilisateurs et paramètres serveur

Cliquez sur **Paramètres** dans la barre du haut pour accéder à :

- **Mon compte** : changer son propre mot de passe (tous les comptes), et
  activer/désactiver la **double authentification (2FA)** — un code à
  usage unique généré par une application d'authentification (Google
  Authenticator, Authy, 2FAS, ...), en plus du mot de passe. Activation :
  *Paramètres → Mon compte → Activer la double authentification*, scanner
  le QR code (ou saisir la clé manuellement), puis confirmer avec le
  premier code généré — la 2FA ne s'active vraiment qu'une fois ce code
  vérifié, pas dès le scan. Une fois activée, le mot de passe seul ne
  suffit plus à se connecter ; désactiver demande de ressaisir le mot de
  passe.
- **Utilisateurs** *(administrateurs uniquement)* : créer des comptes,
  changer le rôle d'un compte (**Administrateur** ou **Lecteur**), supprimer
  un compte, et — pour un compte **Lecteur** — cocher précisément ce qu'il a
  le droit de faire :
  - `Gérer les caméras` : ajouter/modifier/supprimer une caméra, assistant
    ONVIF/marque, programmation de l'enregistrement, réglages de détection
    de mouvement.
  - `Piloter le PTZ` : coché par défaut pour un nouveau lecteur (comportement
    historique) ; décochable si vous voulez un compte strictement
    visionnage.
  - `Supprimer des enregistrements`.
  - `Télécharger des enregistrements` : coché par défaut pour un nouveau
    lecteur. Distinct du simple visionnage : un lecteur peut toujours lire
    un enregistrement dans le lecteur intégré même sans cette permission
    (c'est ce que fait le bouton ▶ *Lire*), seul le bouton de téléchargement
    ⬇ (qui enregistre une copie du fichier sur l'appareil) en dépend.
    Pratique pour un compte utilisé surtout en 4G, afin d'éviter des
    téléchargements de vidéos qui consomment du forfait data — le
    visionnage en direct/à la demande reste possible, seule la copie
    locale est bloquée.
  - `Gérer les paramètres serveur` (rétention, disque, HLS, vignettes —
    voir ci-dessous —, gestion de l'annuaire *Mes systèmes*, et
    configuration des notifications webhook/e-mail).

  Un administrateur a toujours accès à tout, quoi que ces cases indiquent.
  La gestion des comptes elle-même (créer/supprimer un utilisateur, changer
  un rôle ou des permissions) reste réservée aux administrateurs — un
  lecteur ne peut jamais s'accorder plus de droits, même avec toutes les
  permissions ci-dessus cochées. L'API refuse toute action non autorisée
  même en appel direct (403), la restriction n'est pas qu'une question
  d'affichage. Il est impossible de supprimer ou de rétrograder le dernier
  compte administrateur restant, pour ne jamais se retrouver sans accès
  admin.
- **Paramètres serveur** *(administrateurs, ou un lecteur avec la
  permission `Gérer les paramètres serveur`)* : rétention, seuil d'espace
  disque libre, durée des fichiers d'enregistrement, réglages HLS et
  vignettes — les mêmes réglages que les variables d'environnement
  `NVR_*` ci-dessous, mais modifiables sans redémarrer le conteneur.
  L'enregistrement est appliqué immédiatement et les flux caméra en cours
  redémarrent brièvement pour prendre en compte les nouveaux réglages
  (segments, HLS, vignettes).

`NVR_ADMIN_USERNAME`/`NVR_ADMIN_PASSWORD` ne servent qu'à créer le tout
premier compte administrateur au premier démarrage (quand aucun utilisateur
n'existe encore) ; une fois ce compte créé, ces variables n'ont plus aucun
effet et la gestion des comptes se fait entièrement depuis la page
**Paramètres**.

**Protection anti-bruteforce** : après 5 échecs de connexion consécutifs sur
un même compte (en 5 minutes), ce compte est bloqué 5 minutes avant de
pouvoir retenter — même avec le bon mot de passe. Réglable via
`NVR_LOGIN_MAX_ATTEMPTS`/`NVR_LOGIN_ATTEMPT_WINDOW_SECONDS`/
`NVR_LOGIN_LOCKOUT_SECONDS`. Le blocage est par compte (pas par IP) : deux
appareils derrière la même IP partagée (4G, routeur familial) ne se
bloquent pas mutuellement.

## HTTPS

Par défaut, le serveur ne parle que HTTP en clair - mots de passe et flux
vidéo circulent alors sans chiffrement sur le réseau. Deux façons de passer
en HTTPS, selon votre situation :

- **Reverse proxy (recommandé si vous avez un vrai nom de domaine)** :
  placez [Caddy](https://caddyserver.com/) ou Nginx + Let's Encrypt devant
  le NVR - c'est ce qui donne un certificat public reconnu par tous les
  navigateurs sans avertissement.
- **HTTPS natif (pratique pour un boîtier autonome sans domaine)** :
  générez un certificat auto-signé avec
  `./scripts/generate-self-signed-cert.sh`, renseignez
  `NVR_SSL_CERTFILE`/`NVR_SSL_KEYFILE` (le script affiche les valeurs à
  copier), puis lancez le serveur avec `python -m app.main` au lieu de
  `uvicorn app.main:app ...` (l'image Docker le fait déjà). Le navigateur
  affichera un avertissement "connexion non privée" à accepter une fois
  (certificat auto-signé, non reconnu par une autorité publique) - c'est
  attendu, le trafic est bien chiffré malgré l'avertissement.

Sur un réseau local/VPN (Tailscale, WireGuard) déjà chiffré de bout en
bout, HTTP simple reste raisonnable ; ces deux options s'adressent surtout
à un accès direct depuis Internet.

## Regarder depuis le téléphone

- **Sur le même réseau Wi-Fi** : ouvrez `http://<ip-locale-du-serveur>:8000`
  dans le navigateur du téléphone.
- **En scannant un QR code** : une fois connecté depuis un premier appareil,
  ouvrez **Paramètres → Accéder depuis un téléphone** : un QR code y encode
  l'adresse du serveur telle que vue par ce navigateur (IP locale, nom
  Tailscale, domaine derrière un reverse proxy...). Scannez-le avec
  l'appareil photo du téléphone pour ouvrir directement l'interface, sans
  taper l'adresse à la main.
- **Ajout à l'écran d'accueil (iOS/Android)** : l'interface est une
  [web app installable](https://developer.mozilla.org/fr/docs/Web/Progressive_web_apps)
  (icône + mode plein écran sans barre d'adresse). Sur iOS : Safari →
  Partager → *Sur l'écran d'accueil*. Sur Android : Chrome propose
  *Ajouter à l'écran d'accueil* / *Installer l'application* dans son menu.
  Une fois ajoutée, l'icône NVR s'ouvre en plein écran comme une app.
- **À distance (hors du domicile)** : n'exposez pas ce service directement
  sur Internet sans précaution. La façon la plus simple et la plus sûre est
  d'installer un VPN personnel comme [Tailscale](https://tailscale.com/) ou
  [WireGuard](https://www.wireguard.com/) sur le serveur et le téléphone : le
  téléphone accède alors au NVR comme s'il était sur le réseau local, sans
  ouvrir aucun port sur votre box internet. Si vous exposez malgré tout le
  service sur Internet, placez-le derrière un reverse proxy HTTPS (ex.
  Caddy, Nginx + Let's Encrypt) et gardez un mot de passe fort.

## Plusieurs boîtiers NVR : l'annuaire « Mes systèmes »

Si vous gérez plusieurs installations NVR séparées (une par site — maison,
chalet, local pro...), chacune avec ses propres caméras et son propre
compte, la page **Mes systèmes** (lien dans la barre du tableau de bord)
tient l'annuaire de tous vos boîtiers :

- **Ajouter un système** : un nom, une adresse (IP ou domaine, avec ou
  sans port — `192.168.1.50:8000` suffit, `http://` est ajouté
  automatiquement), et une note optionnelle. Réservé aux comptes avec la
  permission *Gérer les paramètres serveur*.
- **État en ligne / hors ligne** : vérifié directement par le navigateur de
  l'appareil qui affiche la page (pas par le serveur) — c'est volontaire,
  puisque la joignabilité dépend d'où vous êtes à cet instant. Un système
  peut donc apparaître hors ligne depuis votre téléphone en 4G mais en
  ligne depuis l'ordinateur de la maison, et inversement.
- **Cliquer sur l'adresse** ouvre l'interface de ce système dans un nouvel
  onglet. Chaque boîtier reste totalement indépendant : pas de compte ni
  de données partagées entre eux, uniquement ce carnet d'adresses.

Ce n'est qu'un annuaire — il n'établit aucune connexion entre vos NVR ni
ne centralise leurs caméras ; il vous fait juste gagner le temps de
retaper chaque adresse.

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

### Où brancher le disque dur ?

Deux topologies possibles selon où vit le disque dur physiquement :

- **Disque branché sur la machine qui fait tourner le NVR (recommandé)** :
  un mini PC, un NAS ou un Raspberry Pi sur le même site que les caméras et
  le Peplink, avec le disque en USB/SATA local (`NVR_DISK_PATH` pointe
  directement dessus). Le Peplink ne sert alors que de liaison réseau/4G,
  jamais de stockage. C'est la topologie la plus simple et la plus fiable
  (écriture disque locale, aucune dépendance réseau pour enregistrer), et
  celle décrite dans les sections *Démarrage rapide* ci-dessus.
- **Disque branché sur le port USB du Peplink lui-même** (certains modèles
  exposent leur port USB comme partage réseau SMB/NFS) : possible, mais le
  Peplink ne fait pas tourner le NVR — vous avez toujours besoin d'une
  machine séparée (mini PC/NAS/Raspberry Pi) qui monte ce partage réseau au
  niveau du système d'exploitation, puis pointe `NVR_DISK_PATH` sur ce point
  de montage. Concrètement, sur la machine qui fait tourner le NVR :
  1. Montez le partage exposé par le Peplink comme n'importe quel partage
     réseau, par ex. via `/etc/fstab` (Linux) :
     ```
     //192.168.50.1/nvr-disk /mnt/peplink-disk cifs credentials=/root/.peplink-creds,_netdev,x-systemd.automount,vers=3.0,uid=1000,gid=1000 0 0
     ```
     (`_netdev`/`x-systemd.automount` évitent que le montage bloque le
     démarrage si le Peplink n'est pas encore joignable ; adaptez `vers=`
     et les identifiants à votre modèle - certains Peplink parlent NFS au
     lieu de SMB/CIFS.)
  2. Pointez `NVR_DISK_PATH` (Docker) ou `NVR_DATA_DIR` (sans Docker) sur
     ce point de montage (`/mnt/peplink-disk` ci-dessus) - l'application ne
     voit alors qu'un dossier normal, elle n'a pas besoin de savoir que
     c'est un partage réseau.
  3. **Important** : passez `NVR_REQUIRE_EXISTING_DATA_DIR=true`. Sans ça,
     si le service démarre avant que le montage réseau soit prêt (ordre de
     démarrage, Peplink qui redémarre...), le dossier serait simplement
     recréé vide en local et le NVR enregistrerait silencieusement sur le
     disque local au lieu du partage - vos enregistrements sembleraient
     fonctionner mais ne seraient pas là où vous les cherchez, et
     réapparaîtraient masqués sous le point de montage une fois celui-ci
     rétabli. Avec cette option, le service refuse de démarrer tant que le
     point de montage n'existe pas réellement (Docker `restart:
     unless-stopped` le fait alors retenter automatiquement).
  4. Gardez à l'esprit qu'un enregistrement continu (écriture ffmpeg toutes
     les quelques secondes) est plus exigeant pour un partage réseau qu'un
     usage fichiers occasionnel : préférez un lien filaire stable entre le
     NVR et le Peplink, surveillez l'état `Erreur` des caméras (symptôme
     d'écritures qui échouent), et si la fiabilité n'est pas suffisante,
     revenez à la première topologie (disque local) et utilisez plutôt le
     partage Peplink pour de l'archivage ponctuel, pas l'enregistrement
     continu.

## Configuration (variables d'environnement)

| Variable | Défaut | Description |
|---|---|---|
| `NVR_DATA_DIR` | `data` | Dossier racine (enregistrements, config, HLS) |
| `NVR_REQUIRE_EXISTING_DATA_DIR` | `false` | Si `true`, refuse de demarrer tant que `NVR_DATA_DIR` n'existe pas deja au lieu de le creer - a activer quand `NVR_DATA_DIR` est un partage reseau monte (ex. disque sur le port USB d'un Peplink), voir *Ou brancher le disque dur ?* ci-dessus |
| `NVR_ADMIN_USERNAME` | `admin` | Identifiant du premier compte administrateur, créé **une seule fois** au tout premier démarrage (sans effet ensuite — voir *Comptes utilisateurs et paramètres serveur*) |
| `NVR_ADMIN_PASSWORD` | `changeme` | Mot de passe du premier compte administrateur (**à changer**, idem) |
| `NVR_SECRET_KEY` | *(généré et conservé automatiquement)* | Clé de signature des sessions |
| `NVR_LOGIN_MAX_ATTEMPTS` | `5` | Nombre d'échecs de connexion tolérés pour un même compte avant blocage temporaire (anti-bruteforce) |
| `NVR_LOGIN_ATTEMPT_WINDOW_SECONDS` | `300` | Fenêtre de temps sur laquelle les échecs sont comptés |
| `NVR_LOGIN_LOCKOUT_SECONDS` | `300` | Durée du blocage une fois le seuil atteint |
| `NVR_SEGMENT_SECONDS` | `600` | Durée d'un fichier d'enregistrement (secondes) — modifiable aussi depuis **Paramètres** |
| `NVR_RETENTION_DAYS` | `14` | Suppression des enregistrements plus vieux que N jours — idem |
| `NVR_MIN_FREE_DISK_PERCENT` | `10` | Purge des plus anciens enregistrements sous ce seuil d'espace libre — idem |
| `NVR_HLS_SEGMENT_SECONDS` | `2` | Taille des segments HLS (latence du direct) — idem |
| `NVR_HLS_LIST_SIZE` | `6` | Nombre de segments HLS conservés dans la playlist (marge sur liaison instable) — idem |
| `NVR_THUMBNAIL_INTERVAL_SECONDS` | `60` | Intervalle par défaut entre deux vignettes (secondes), surchargeable par caméra — idem |
| `NVR_THUMBNAIL_CHECK_INTERVAL_SECONDS` | `30` | Fréquence de vérification des nouveaux enregistrements à traiter — idem |
| `NVR_MOTION_CHECK_INTERVAL_SECONDS` | `5` | Fréquence d'échantillonnage pour la détection de mouvement (caméras avec `motion_enabled`) — idem |
| `NVR_PORT` | `8000` | Port d'écoute |
| `NVR_SSL_CERTFILE` / `NVR_SSL_KEYFILE` | *(vide, HTTP)* | Chemins vers un certificat/clé TLS - lancez alors avec `python -m app.main` pour du HTTPS natif (voir *HTTPS* ci-dessus) |

Les lignes marquées « idem » ci-dessus ne fixent qu'une valeur de démarrage :
un administrateur peut les changer à tout moment depuis **Paramètres → 
Paramètres serveur** dans l'interface, sans redémarrer le conteneur.

## Structure du dépôt

```
app/
  config.py          configuration (variables d'environnement + surcharges runtime)
  models.py           modèles de données (Camera, User, réglages runtime, ...)
  store.py            persistance des caméras (YAML)
  user_store.py         persistance des comptes utilisateurs (YAML, mots de passe hachés)
  settings_store.py      persistance des réglages serveur modifiables depuis l'UI (YAML)
  systems_store.py        persistance de l'annuaire "Mes systemes" (autres boitiers NVR, YAML)
  notification_settings_store.py  persistance des reglages de notification webhook/e-mail (YAML)
  notifier.py               envoi effectif des notifications (webhook + SMTP), best-effort
  camera_health.py          detecte les transitions hors-ligne/de retour d'une camera pour les notifications
  audit_log.py              journal d'acces aux enregistrements (qui a regarde/telecharge quoi, quand)
  totp.py                   TOTP (RFC 6238) pour la double authentification, code hors dependance
  login_throttle.py         anti-bruteforce du login (blocage temporaire par compte)
  ffmpeg_cmd.py        construction des commandes ffmpeg
  ffmpeg_manager.py    supervision des processus ffmpeg (démarrage/redémarrage)
  retention.py         purge automatique des enregistrements et vignettes
  recordings.py         nommage/parcours des segments enregistrés (partagé)
  thumbnails.py          extraction des vignettes depuis les segments termines
  motion.py               detection de mouvement (diff d'image bas niveau, sans dependance lourde)
  recording_schedule.py   demarre/arrete l'enregistrement selon la grille horaire de chaque camera
  auth.py              authentification par session + comptes (bootstrap, vérification)
  deps.py                dépendances FastAPI (require_auth, require_admin)
  onvif_client.py        client ONVIF (PTZ + decouverte des flux media)
  onvif_discovery.py      recherche de cameras ONVIF sur le reseau (WS-Discovery)
  ptz_registry.py        cache des clients PTZ par caméra
  api/                 routes FastAPI (auth, utilisateurs, paramètres, caméras, médias, PTZ, ONVIF, système)
  static/              interface web (HTML/CSS/JS, sans build)
    manifest.json        manifeste PWA (icone + mode plein ecran a l'ajout sur l'ecran d'accueil)
    icons/                icones de l'app (favicon, apple-touch-icon, icones PWA)
    js/qrcode.min.js       generateur de QR code cote client (vendored, sans dependance externe)
tests/                 tests automatisés (pytest)
pi-image/
  firstboot.sh          script de provisionnement (Docker, clonage, .env, service systemd) pour un Raspberry Pi qui démarre sur son disque
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
