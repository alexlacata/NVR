[← Retour au README](../README.md)

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

Le mot de passe SMTP est chiffré avant d'être écrit sur disque (voir
*Chiffrement des secrets stockés* ci-dessous) — un vol du fichier ou d'une
sauvegarde ne l'expose pas en clair.

## Sauvegarde vers un second emplacement

Le disque local de l'enregistreur est un point de défaillance unique : s'il
tombe en panne, tout est perdu. `NVR_BACKUP_DIR` (chemin vers un second
dossier — NAS monté, second disque, peu importe) active une copie
automatique et périodique des **enregistrements uniquement** (pas les
vignettes ni les segments HLS, éphémères et reconstructibles) vers cette
destination, en tâche de fond (`NVR_BACKUP_CHECK_INTERVAL_SECONDS`, 5
minutes par défaut). Se configure par variable d'environnement uniquement
(redémarrage requis, comme `NVR_DATA_DIR`), mais **Paramètres →
Sauvegarde** affiche l'état (destination, dernière exécution, fichiers
copiés/échoués) et propose un bouton **Sauvegarder maintenant** pour
déclencher une copie immédiate sans attendre le prochain cycle. Un fichier
déjà présent à l'identique (même taille) à la destination n'est pas
recopié ; une destination temporairement injoignable (NAS débranché) ne
bloque rien — les fichiers en échec sont retentés au cycle suivant, avec
une notification (voir *Notifications* ci-dessus) si l'échec persiste.

⚠️ Ceci protège contre une panne de disque, pas contre un incendie/vol qui
détruirait les deux appareils au même endroit : pour une vraie
redondance, la destination de sauvegarde devrait être dans un endroit
physiquement différent (autre pièce, autre site).

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
  passe. À la confirmation, **8 codes de secours à usage unique**
  s'affichent une seule fois (notez-les) : chacun remplace le code de
  l'application le temps d'une connexion si vous perdez votre téléphone —
  saisissez-le dans le même champ que le code à 6 chiffres, au format
  `XXXX-XXXX`. Un compteur indique combien il en reste ; régénérez-les à
  tout moment (mot de passe requis) pour invalider les anciens et en
  obtenir une nouvelle série. Le secret TOTP est chiffré avant d'être
  écrit sur disque (voir *Chiffrement des secrets stockés* ci-dessous) ;
  les codes de secours, eux, sont hachés comme un mot de passe plutôt que
  chiffrés — ils ne sont jamais relus, seulement comparés.
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

  En plus de ces permissions (ce qu'un lecteur a le droit de *faire*), vous
  pouvez restreindre *quelles caméras* il voit : cochez `Limiter l'accès à
  certaines caméras` sous son compte, puis sélectionnez-les une par une —
  par exemple pour qu'une personne qui garde les enfants ne voie que la
  caméra du salon, sans accès aux autres pièces. Sans cette case cochée
  (comportement par défaut), un lecteur voit toutes les caméras. La
  restriction s'applique à tout ce qui concerne cette caméra : direct,
  enregistrements, vignettes, PTZ — un lecteur restreint reçoit une simple
  réponse « caméra introuvable » pour toute caméra hors de sa liste, y
  compris en appel direct à l'API, pas seulement dans l'interface.

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
  [`NVR_*`](installation.md), mais modifiables sans redémarrer le conteneur.
  L'enregistrement est appliqué immédiatement et les flux caméra en cours
  redémarrent brièvement pour prendre en compte les nouveaux réglages
  (segments, HLS, vignettes).

  La conservation des enregistrements (*Paramètres → Réglages du
  serveur*) propose des boutons de préréglage (7, 14, 30 jours) en plus
  d'un nombre de jours personnalisé, et un mode **Écrasement permanent**
  (`retention_days = 0`) : aucune limite de durée, les enregistrements les
  plus anciens ne sont supprimés que lorsque l'espace disque libre passe
  sous le seuil réglé juste en dessous (`min_free_disk_percent`) — un
  enregistrement en boucle continue, comme un DVR classique qui réécrit
  par-dessus les plus vieilles images. Ce seuil d'espace disque
  s'applique quoi qu'il arrive, même avec une durée de conservation
  fixée : c'est le filet de sécurité qui évite de saturer le disque si
  plus de vidéo est produite que prévu.

`NVR_ADMIN_USERNAME`/`NVR_ADMIN_PASSWORD` ne servent qu'à créer le tout
premier compte administrateur au premier démarrage (quand aucun utilisateur
n'existe encore) ; une fois ce compte créé, ces variables n'ont plus aucun
effet et la gestion des comptes se fait entièrement depuis la page
**Paramètres**.

**Plus aucun accès administrateur (mot de passe oublié + 2FA/codes de
secours perdus)** : sans accès admin, personne ne peut réinitialiser un
compte depuis l'interface web. `scripts/account-recovery.py` répare ça
directement sur le fichier de comptes, avec un accès au serveur (ou au
disque de données) :

```bash
export NVR_DATA_DIR=/mnt/disque-nvr   # meme valeur que pour le serveur
python scripts/account-recovery.py list                        # lister les comptes
python scripts/account-recovery.py reset-password admin        # reinitialiser un mot de passe
python scripts/account-recovery.py disable-2fa admin           # en cas de telephone + codes de secours perdus
python scripts/account-recovery.py set-role alice admin        # promouvoir un compte
```

Arrêtez le serveur avant si possible (deux processus qui écrivent le même
fichier en même temps est à éviter, même si les écritures sont atomiques).
Ce script est volontairement une commande hors ligne plutôt qu'un flux « mot
de passe oublié » par e-mail : ce NVR n'a pas d'adresse e-mail par compte,
et un accès serveur est de toute façon le seul recours crédible pour un
logiciel auto-hébergé à instance unique.

**Sessions actives** : la page **Paramètres** liste, pour le compte
connecté, tous les appareils/navigateurs actuellement authentifiés
(navigateur, adresse IP, date de connexion), avec la session en cours
signalée comme telle. Chaque session peut être révoquée individuellement
(icône 🗑) — utile pour couper l'accès à un appareil perdu ou prêté sans
changer son propre mot de passe. La révocation est immédiate et côté
serveur : le jeton de la session visée cesse de fonctionner dès la requête
suivante, ce n'est pas un simple effacement de cookie local. La
déconnexion (`Déconnexion`) révoque de la même façon la session en cours.
Par sécurité, changer son mot de passe révoque automatiquement toutes les
*autres* sessions du compte (celle qui effectue le changement reste
active) : un mot de passe est souvent changé après une suspicion de
compromission, et laisser d'anciennes sessions valides irait à l'encontre
de cette réaction. Les jetons émis avant l'ajout de cette fonctionnalité
restent valables jusqu'à leur expiration naturelle plutôt que de forcer
une reconnexion de tout le monde au déploiement.

**Protection anti-bruteforce** : après 5 échecs de connexion consécutifs sur
un même compte (en 5 minutes), ce compte est bloqué 5 minutes avant de
pouvoir retenter — même avec le bon mot de passe. Réglable via
`NVR_LOGIN_MAX_ATTEMPTS`/`NVR_LOGIN_ATTEMPT_WINDOW_SECONDS`/
`NVR_LOGIN_LOCKOUT_SECONDS`. Le blocage est par compte (pas par IP) : deux
appareils derrière la même IP partagée (4G, routeur familial) ne se
bloquent pas mutuellement.

**Limitation de débit générale de l'API** : au-delà de la protection
anti-bruteforce ci-dessus (spécifique à la connexion), toutes les routes
`/api/*` sont plafonnées à 120 requêtes par minute et par identité — le
compte connecté une fois authentifié, sinon l'adresse IP (typiquement pour
la requête de connexion elle-même). Au-delà, l'API répond `429 Too Many
Requests` avec un en-tête `Retry-After` indiquant dans combien de secondes
retenter. Réglable via `NVR_RATE_LIMIT_MAX_REQUESTS`/
`NVR_RATE_LIMIT_WINDOW_SECONDS`. Comme pour le blocage de connexion, la
limite par compte (plutôt que par IP une fois connecté) évite qu'un
partage d'IP (4G, routeur familial) ne pénalise tout le monde derrière —
et empêche à l'inverse qu'un compte compromis ou un client buggé ne
martèle une route (téléchargements en boucle, appels PTZ répétés...) sans
affecter les autres comptes. Les fichiers statiques (interface web,
vignettes) ne sont pas concernés — seule l'API l'est.

**Chiffrement des secrets stockés** : plusieurs secrets réversibles sont
persistés par le serveur — le mot de passe SMTP (notifications par
e-mail), le secret TOTP de chaque compte (2FA), le mot de passe
ONVIF/interface web de chaque caméra, et le mot de passe du routeur (voir
[*Accès direct à l'interface de la caméra et du routeur*](cameras.md)). Tous
sont chiffrés avant écriture sur disque (`notifications.yaml`,
`users.yaml`, `cameras.yaml`, `router_credentials.yaml`), avec une clé
dérivée de `NVR_SECRET_KEY` (la même déjà utilisée pour signer les
sessions — voir [*Configuration*](installation.md)). Concrètement, un vol du
fichier ou d'une sauvegarde seule (sans `NVR_SECRET_KEY`) n'expose aucun
en clair. Ça ne protège pas contre la compromission du serveur
lui-même : le processus a besoin de la clé pour déchiffrer à la volée
(envoyer un e-mail, vérifier un code 2FA, construire un lien de connexion
automatique), donc une intrusion active sur la machine y a accès de toute
façon — la même limite que le chiffrement de disque. Les autres secrets
du système (mots de passe de compte, codes de secours 2FA) ne sont pas
concernés : ils sont hachés (bcrypt), pas chiffrés — plus fort qu'un
chiffrement réversible pour une valeur qu'on ne
fait jamais que comparer, jamais relire.

