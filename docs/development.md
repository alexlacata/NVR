[← Retour au README](../README.md)

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
  backup.py                 copie periodique des enregistrements vers un second emplacement (NVR_BACKUP_DIR)
  login_throttle.py         anti-bruteforce du login (blocage temporaire par compte)
  rate_limiter.py           limitation de débit générale de l'API (au-delà du login)
  session_store.py          persistance des sessions actives (YAML), pour lister/révoquer par compte
  secrets_crypto.py         chiffrement au repos des secrets stockes (SMTP, TOTP, caméra, routeur - cle derivee de NVR_SECRET_KEY)
  router_credentials_store.py  persistance de l'identifiant du routeur (YAML), pour le lien d'acces rapide du tableau de bord
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
scripts/
  account-recovery.py     recuperation hors ligne d'un compte (mot de passe/2FA/role) sans acces admin
  generate-self-signed-cert.sh  generation d'un certificat auto-signe pour le HTTPS natif
pi-image/
  firstboot.sh          script de provisionnement (Docker, clonage, .env, service systemd) pour un Raspberry Pi qui démarre sur son disque
.github/workflows/
  tests.yml               integration continue : lance la suite de tests sur chaque push/pull request
```

## Mettre à jour / revenir en arrière

Appliquer une mise à jour et revenir à la version précédente passent par
la même opération simple (`git checkout` + reconstruction) - jamais par
une modification manuelle de fichiers, ce qui garantit que chaque
changement reste isolé et réversible plutôt que de s'accumuler de façon
incontrôlée.

**Mettre à jour** (sur le Pi, ou toute autre machine qui fait tourner le
NVR) :
```bash
cd ~/nvr   # ou l'emplacement de votre installation
git pull
docker compose up -d --build
```

**Revenir à la version précédente** si une mise à jour pose problème -
listez d'abord les versions disponibles, puis basculez dessus :
```bash
git tag -l                          # liste les versions reperees
git checkout v1.0.0                 # remplacez par la version voulue
docker compose up -d --build
```

Ni la mise à jour ni le retour en arrière ne touchent à vos données
(caméras, enregistrements, comptes) : elles vivent dans `NVR_DATA_DIR`
(un volume Docker séparé, jamais versionné avec le code), pas dans le
dépôt. Un retour en arrière arrête brièvement tous les flux caméra le
temps de reconstruire le conteneur (quelques secondes), sans aucune
perte d'enregistrement.

Pour revenir ensuite à la dernière version (sortir du mode "figé" sur un
ancien tag) :
```bash
git checkout claude/nvr-multi-stream-gateway-fzb8xm
git pull
docker compose up -d --build
```

## Robustesse et limites connues

Quelques points à avoir en tête pour un usage réel, au-delà de ce que le
logiciel gère déjà tout seul (auto-restart des flux ffmpeg, purge
automatique du disque, sauvegarde optionnelle, alertes — voir plus haut) :

- **Redondance disque (RAID)** : ce NVR traite `NVR_DATA_DIR` comme un
  disque unique — il ne fait aucune réplication lui-même. La sauvegarde
  ([*Sauvegarde vers un second emplacement*](administration.md)) protège contre la
  perte de données, mais avec un délai (le cycle de sauvegarde) et sans
  continuité de service : si le disque principal meurt, l'enregistrement
  s'arrête jusqu'à intervention. Pour de la vraie redondance *sans coupure*
  (le service continue si un disque tombe), montez `NVR_DATA_DIR` sur un
  volume RAID1/RAID5 (mdadm, ou le RAID matériel d'un NAS) plutôt que sur
  un disque simple — la sauvegarde vers un second emplacement reste
  recommandée en plus, pas à la place, pour couvrir un sinistre qui
  toucherait tout le boîtier (incendie, vol).
- **Usage prolongé avec plusieurs flux simultanés** : chaque caméra
  supervise deux process `ffmpeg` (enregistrement + direct) ; sur du
  matériel modeste (Raspberry Pi, mini-PC bas de gamme), testez la charge
  réelle (CPU, RAM, débit disque) avec le nombre de caméras et la
  résolution que vous comptez utiliser *avant* un déploiement définitif —
  le logiciel n'impose pas de limite artificielle, mais le matériel si.
- **Profils de marque de caméra non validés sur du matériel réel** :
  l'assistant d'URL par marque (Hikvision, Dahua, Reolink, etc. — voir
  *Vous ne connaissez pas l'URL de la caméra ?*) génère des chemins RTSP
  d'après la documentation publique de chaque marque ; aucun n'a été
  vérifié contre une caméra physique de la marque en question. Un chemin
  peut varier selon le modèle/firmware exact — si l'URL générée ne
  fonctionne pas du premier coup, préférez la détection ONVIF (qui
  interroge la caméra directement) avant de suspecter un bug.
- **Aspect légal (vidéosurveillance)** : filmer un espace accessible à
  des tiers (rue, entrée commune, voisinage) est encadré par la loi selon
  votre pays/région (durée de conservation, panneau d'information
  obligatoire, déclaration éventuelle, zones interdites comme la voie
  publique ou la propriété du voisin selon les cas). Ce logiciel ne vous
  dispense pas de vérifier ce qui s'applique à votre situation — c'est une
  question juridique, pas technique.
- **Horodatage et intégrité pour un usage "preuve"** : l'empreinte SHA256
  à la demande ([*Relire un enregistrement*](cameras.md)) permet de vérifier
  qu'une copie téléchargée n'a pas été altérée, et le journal d'activité
  trace qui a consulté/téléchargé quoi. Il n'y a en revanche pas
  d'horodatage signé/certifié par un tiers de confiance — si vos
  enregistrements doivent servir de preuve dans une procédure formelle,
  renseignez-vous sur les exigences spécifiques applicables (elles varient
  largement selon le contexte).
- **Enregistrements non chiffrés sur disque** : contrairement au mot de
  passe SMTP et au secret TOTP ([*Chiffrement des secrets stockés*](administration.md)),
  les fichiers vidéo eux-mêmes (`NVR_DATA_DIR/recordings`,
  vignettes, HLS) sont écrits en clair. Ce n'est pas un oubli : les
  chiffrer au niveau applicatif n'apporterait rien ici. Il faudrait de
  toute façon garder la clé accessible en permanence au processus pour
  déchiffrer à la demande (relecture, vignettes, purge de rétention,
  export) — exactement le même compromis que pour le mot de passe SMTP/le
  secret TOTP, mais sur des fichiers bien plus gros et bien plus souvent
  lus, pour un coût CPU/IO ajouté à chaque lecture ou écriture sans
  bénéfice de sécurité supplémentaire par rapport à la bonne réponse à ce
  problème : le **chiffrement de disque au niveau du système
  d'exploitation** (LUKS sur Linux, BitLocker sur Windows, FileVault sur
  macOS), qui protège tout `NVR_DATA_DIR` — enregistrements compris — dans
  le cas qui compte réellement, le vol physique du disque ou du boîtier
  éteint, sans toucher au logiciel ni à ses performances pendant qu'il
  tourne (le disque est déchiffré une fois au démarrage, transparent
  ensuite). Sur un boîtier qui reste allumé en continu (le cas normal
  d'un NVR), la protection couvre le scénario "quelqu'un repart avec le
  disque" ; elle ne protège pas contre un accès à la machine pendant
  qu'elle tourne, montée et déverrouillée — même limite, déjà mentionnée
  ci-dessus, que le chiffrement des secrets applicatifs.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Un test de bout en bout (`tests/test_smoke_pipeline.py`) démarre un vrai
processus `ffmpeg` sur une source de test et vérifie que l'enregistrement et
le flux HLS sont bien produits sur disque ; il est automatiquement ignoré si
`ffmpeg` n'est pas installé.

**Intégration continue** : `.github/workflows/tests.yml` exécute
l'intégralité de cette suite de tests (avec `ffmpeg` installé, donc y
compris le test de bout en bout ci-dessus) sur chaque `push` et chaque
pull request, quelle que soit la branche — une régression ne peut donc pas
être fusionnée silencieusement. Voir l'onglet **Actions** du dépôt GitHub
pour le résultat des exécutions.

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
