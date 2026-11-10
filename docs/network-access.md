[← Retour au README](../README.md)

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

**Cookie de session et HTTPS** : le cookie de connexion n'est marqué
`Secure` (envoyé uniquement sur une connexion HTTPS, jamais en clair) que
si le serveur sait qu'il est bien servi en HTTPS — automatique avec
`NVR_SSL_CERTFILE`/`NVR_SSL_KEYFILE` (HTTPS natif ci-dessus). Avec un
reverse proxy qui termine le HTTPS à votre place (le serveur NVR, lui, ne
reçoit que du HTTP du proxy), ajoutez `NVR_BEHIND_TLS_PROXY=true` pour
l'indiquer explicitement — ce réglage n'est jamais déduit automatiquement
d'un en-tête de la requête (`X-Forwarded-Proto`), qui pourrait être
falsifié par un client pour se faire passer à tort pour une connexion
sécurisée.

**En-têtes de sécurité HTTP** : chaque réponse (API comme pages web)
inclut `X-Frame-Options: DENY` et une CSP avec `frame-ancestors 'none'`
(empêche un autre site d'intégrer l'appli dans une `<iframe>` invisible
pour piéger un clic — attaque dite de clickjacking), `X-Content-Type-Options:
nosniff`, une `Content-Security-Policy` qui limite scripts/styles/images/
médias à la même origine, et `Permissions-Policy` qui désactive caméra/
micro/géolocalisation du navigateur (inutiles ici — l'appli parle
directement aux caméras IP, pas via le navigateur). `Strict-Transport-
Security` s'ajoute automatiquement dès que le HTTPS est actif (natif ou
`NVR_BEHIND_TLS_PROXY`), par cohérence avec le cookie de session ci-dessus.

## Regarder depuis le téléphone

- **Consommation de données du tableau de bord** : chaque vignette de
  caméra y affiche une simple image fixe (rafraîchie environ toutes les
  30 secondes), pas un direct vidéo en continu — ouvrir le tableau de
  bord avec 10 caméras ne lance donc pas 10 flux vidéo simultanés. Cliquez
  sur l'image (bouton **▶**) pour ouvrir cette caméra et lancer son vrai
  direct vidéo, un flux à la fois. Utile en 4G, où lire N flux HLS en
  parallèle juste pour afficher un tableau de bord consommerait vite un
  forfait de données.
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
- **Cliquer sur l'adresse** (le « chemin distant ») ouvre l'interface de ce
  système dans un nouvel onglet. Chaque boîtier reste totalement
  indépendant : pas de compte ni de données partagées entre eux,
  uniquement ce carnet d'adresses.
- **La petite porte 🚪** à côté de l'adresse, quand elle apparaît, est un
  « chemin root » distinct : un accès SSH/terminal à la machine derrière
  ce système, pas à l'interface web du NVR. Même principe que l'accès SSH
  des caméras et du routeur (voir [*Accès direct à l'interface de la caméra et du routeur*](cameras.md)) — juste un utilisateur et un
  port, jamais de mot de passe stocké ni demandé. Rien à saisir à
  l'ajout : chaque système reçoit automatiquement `root` / port `22` (les
  valeurs les plus courantes), donc la porte apparaît d'elle-même. Si
  votre machine utilise un autre utilisateur/port, ou n'a pas de SSH du
  tout, ajustez-le ou videz-le à tout moment via les deux petits champs
  "SSH" sous chaque entrée existante (réservé aux comptes avec la
  permission *Gérer les paramètres serveur*) ; laissez le champ
  utilisateur vide pour que la porte n'apparaisse plus.

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
  celle décrite dans la section [*Démarrage rapide*](../README.md#démarrage-rapide-docker-recommandé).
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

