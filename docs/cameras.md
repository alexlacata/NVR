[← Retour au README](../README.md)

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
  l'avance — voir la note Docker du [démarrage rapide](../README.md#démarrage-rapide-docker-recommandé)
  pour que cela fonctionne en conteneur.
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

Sur cette page, les réglages optionnels (programmation, bande passante,
vignettes, PTZ, interface web, SSH, détection de mouvement) sont repliés
par défaut - seuls le nom, le type, l'URL et les cases activée/enregistrer
restent visibles d'emblée, pour ne pas noyer une configuration simple sous
des champs rarement utilisés. Chaque section s'ouvre automatiquement une
fois si elle est déjà configurée (ex. le PTZ reste ouvert si vous l'avez
activé), et son intitulé indique son état en un coup d'œil sans avoir à
cliquer.

### Accès direct à l'interface de la caméra et du routeur

Sur le tableau de bord, chaque vignette de caméra affiche deux petits
liens sous son nom : **📷 &lt;adresse IP&gt;** et **📡 Routeur**. Ils
ouvrent, dans un nouvel onglet, l'interface web native de la caméra
(`http://<ip-camera>/`) et celle présumée du routeur (`http://<ip>.1/` —
la convention classique du ".1" de la passerelle du même sous-réseau que
la caméra). L'adresse est déduite automatiquement de l'URL déjà
configurée pour la caméra (RTSP/ONVIF) — rien à saisir en plus pour ça.
Ces mêmes liens apparaissent aussi directement sur la page de chaque
caméra (pas seulement sur le tableau de bord), juste sous le direct
vidéo.

**Connexion automatique (quand les identifiants sont connus)** : si vous
renseignez les identifiants de connexion de la caméra et/ou du routeur
(voir ci-dessous), le lien les intègre directement dans l'adresse
(authentification HTTP Basic) — un clic ouvre alors la page déjà
connectée, sans ressaisir de mot de passe. Ça ne marche que si
l'interface de l'appareil utilise elle-même ce mécanisme (fréquent sur
les routeurs et beaucoup de caméras bas de gamme/anciennes ; une
interface web plus moderne avec son propre formulaire de connexion
JavaScript l'ignorera). Dans ce cas, un bouton **📋** à côté du lien copie
"utilisateur / mot de passe" dans le presse-papier pour les coller
manuellement dans le formulaire.

**Sur iPhone/iPad, ce lien reste volontairement une simple adresse, sans
identifiants intégrés** : iOS (Safari, mais aussi Chrome, Firefox... tous
les navigateurs y tournent sur le même moteur WebKit imposé par Apple)
refuse silencieusement d'ouvrir un lien contenant des identifiants —
aucune erreur, aucun onglet ne s'ouvre, ça ne fait juste rien. C'est
détecté automatiquement : sur ces appareils, le lien reste cliquable
(adresse simple) et le bouton **📋** copie les identifiants pour les
coller vous-même. Sur ordinateur et Android, la connexion automatique
fonctionne normalement.

Où sont renseignés ces identifiants :

- **Caméra** : sur la page de la caméra, section *Interface web de la
  caméra* *(administrateurs, ou un lecteur avec la permission `Gérer les
  caméras`)* — utilisateur/mot de passe de l'interface d'administration
  native de la caméra (pas ceux du NVR). Si vous avez déjà renseigné des
  identifiants ONVIF pour le PTZ (souvent le même compte), laissez ces
  champs vides : ils sont réutilisés automatiquement. Le mot de passe est
  chiffré au repos comme les autres secrets stockés (voir [*Chiffrement
  des secrets stockés*](administration.md)). Un compte lecteur sans cette permission
  voit toujours le lien **📷** de la caméra, mais sans connexion
  automatique ni bouton de copie — ces mots de passe ne lui sont jamais
  transmis.
- **Routeur** : dans **Paramètres → Routeur** *(administrateurs, ou un
  lecteur avec la permission `Gérer les paramètres serveur`)* — un seul
  identifiant global, réutilisé pour toutes les caméras. Réservé à ce
  niveau de permission car, contrairement à l'identifiant d'une caméra,
  celui du routeur donne potentiellement accès à tout le réseau (Wi-Fi,
  redirections de ports...) ; un compte lecteur sans cette permission voit
  toujours le lien **Routeur**, mais sans connexion automatique ni bouton
  de copie.

**HTTP ou HTTPS** : à côté de ces identifiants, une case *Interface
accessible en HTTPS* (décochée par défaut) fait passer le lien
correspondant en `https://` plutôt que `http://` — utile puisque
beaucoup d'interfaces d'administration de caméras et de routeurs ne sont
joignables qu'en HTTPS. Le certificat de ces interfaces est presque
toujours auto-signé (l'appareil n'a pas de nom de domaine public) :
attendez-vous à un avertissement de sécurité du navigateur à l'ouverture,
normal ici, à valider une fois par appareil.

**Accès SSH** : un troisième lien optionnel, **🖥 SSH**, apparaît si vous
renseignez un utilisateur SSH pour la caméra (sa propre page) ou pour le
routeur (Paramètres → Routeur) — le port est ajusté à côté (22 par
défaut). Contrairement au lien d'interface web ci-dessus, **aucun mot de
passe SSH n'est jamais demandé ni stocké** : SSH n'a pas d'équivalent à
l'authentification HTTP Basic, et enregistrer un mot de passe root SSH
serait bien plus risqué qu'un mot de passe d'interface web (un accès SSH
root donne un contrôle total du système, pas juste de son interface).
Concrètement :

- Le lien `ssh://utilisateur@ip:port` ne fait quelque chose que si votre
  système a un client SSH associé à ce protocole (courant sur Linux/macOS,
  pas garanti sur Windows sans installation tierce) — et il ne connecte
  jamais automatiquement, vous entrez votre mot de passe (ou passphrase de
  clé) normalement.
- Le bouton **📋** à côté copie la commande prête à coller dans un
  terminal (`ssh utilisateur@ip` ou `ssh utilisateur@ip -p port` si le
  port n'est pas 22).
- La plupart des caméras IP grand public n'exposent aucun serveur SSH —
  laissez ces champs vides dans ce cas, le lien SSH n'apparaît pas. C'est
  plus courant sur des routeurs orientés utilisateurs avancés (OpenWrt,
  pfSense, Ubiquiti...) ou du matériel à base de Linux (ex. un Raspberry
  Pi sur un site distant).

Trois choses à garder en tête, identifiants renseignés ou non :

- L'adresse ".1" est un raccourci, pas une découverte réseau : si votre
  routeur est ailleurs sur ce sous-réseau (passerelle à ".254", VLAN,
  etc.), renseignez son adresse exacte une bonne fois pour toutes dans
  **Paramètres → Routeur → Adresse IP du routeur** plutôt que de la
  corriger à chaque fois dans la barre d'adresse — cette valeur, quand
  elle est renseignée, remplace systématiquement la déduction automatique.
- Ces liens ouvrent la page de connexion **propre à la caméra ou au
  routeur**, pas un accès magique. Le NVR n'a et ne peut avoir aucun
  moyen de s'authentifier à votre place sur un appareil tiers au-delà de
  rejouer ce que vous lui avez explicitement confié.
- Ces liens n'apparaissent que si l'URL configurée contient une adresse
  IPv4 simple (ex. `192.168.1.42`) — pas pour une caméra jointe via un nom
  d'hôte/DDNS, où deviner une passerelle locale n'aurait pas de sens.

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

Deux curseurs dans cette même section règlent la vitesse des mouvements
(1-100%, 50% par défaut) : **vitesse de déplacement** (haut/bas/gauche/
droite) et **vitesse de zoom**, séparées car le moteur de zoom d'une
caméra est souvent bien plus lent ou rapide que son moteur de rotation.
Une vitesse plus basse donne un pilotage plus précis (petits mouvements
fins) ; plus haute, elle parcourt une grande scène plus vite. Le réglage
s'applique dès l'enregistrement, sans recharger la page.

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
- **Type de zone** : deux façons d'utiliser la même grille superposée à
  l'aperçu de la caméra, selon ce qui est le plus simple à décrire pour
  votre scène :
  - **Zone à ignorer (masquage, par défaut)** : cliquez sur les cases à
    exclure (une route passante, un arbre, une fenêtre de voisinage...) ;
    tout le reste du champ de vision reste surveillé normalement.
  - **Zone à surveiller (détection uniquement)** : à l'inverse, cliquez sur
    la ou les seules cases à surveiller (une porte, un portail...) ; tout
    le reste de l'image est ignoré. Si aucune case n'est cochée dans ce
    mode, rien n'est surveillé — c'est un réglage valide (« ne rien
    surveiller »), pas une erreur.

Un badge **Mouvement** apparaît en haut de la page de la caméra dès qu'un
mouvement est en cours de détection, et l'heure du dernier mouvement détecté
s'affiche sous le réglage de sensibilité. La fréquence de vérification
(`NVR_MOTION_CHECK_INTERVAL_SECONDS`, 5 secondes par défaut) est un réglage
serveur global.

**Mouvements détectés** : dès que la détection est activée, une liste des
derniers mouvements apparaît sur la page de la caméra (entre la ligne du
temps et les enregistrements), accessible à tout compte pouvant voir la
caméra (pas seulement les administrateurs). Chaque ligne ouvre, en un
clic sur **▶ Voir**, un court passage d'environ 30 secondes autour du
moment détecté - un raccourci pratique pour vérifier rapidement de quoi
il s'agissait sans faire défiler toute la journée. La ligne du temps
complète au-dessus reste utilisable normalement pour revoir n'importe
quelle autre période à votre rythme ; ce raccourci n'y change rien,
il ne fait qu'y amener plus vite.

