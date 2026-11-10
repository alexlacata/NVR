# Annuaire NVR

Une page séparée qui liste tous vos boîtiers NVR (nom, adresse, notes),
avec un badge "en ligne / hors ligne" vérifié directement par votre
navigateur. Volontairement indépendante du NVR lui-même : elle tourne sur
sa propre machine, pas sur un Raspberry Pi qui héberge un boîtier NVR.
Résultat : même si tous vos boîtiers NVR tombent en même temps, cette
page reste joignable et continue d'afficher la dernière liste connue, et
vous pouvez l'ouvrir depuis votre téléphone ou votre ordinateur, où que
vous soyez - c'est la même liste partout.

Ce dossier (`nvr-directory/`) est un service Docker à part entière, qui
ne dépend d'aucun fichier du reste du dépôt (`app/`) : vous pouvez le
copier seul sur une autre machine sans rien emporter d'autre.

## Ce qu'il vous faut

1. **Un petit serveur (VPS)** chez un hébergeur - par ex. Hetzner,
   Scaleway, OVH (environ 3 à 6 €/mois pour le plus petit modèle,
   largement suffisant ici). Prenez une image **Ubuntu** (22.04 ou plus
   récent). L'hébergeur vous donnera une **adresse IP publique** - notez-la.
2. **Un nom de domaine (ou sous-domaine)** qui pointe vers cette adresse
   IP - nécessaire pour que le HTTPS automatique fonctionne (voir
   ci-dessous). Si vous possédez déjà un nom de domaine, créez-y un
   enregistrement DNS de type **A** (ex. `annuaire.mondomaine.fr` →
   l'adresse IP du VPS) depuis l'interface de votre registrar. Si vous
   n'en avez pas, un service gratuit comme [DuckDNS](https://www.duckdns.org/)
   vous donne un sous-domaine (ex. `moncompte.duckdns.org`) à pointer vers
   cette même adresse IP, en quelques clics et sans frais.

## Installation sur le VPS

Connectez-vous au VPS en SSH (l'hébergeur vous explique comment, en
général `ssh root@<adresse IP>` avec le mot de passe ou la clé qu'il vous
a fourni), puis :

```bash
# Installer Docker (une seule fois)
curl -fsSL https://get.docker.com | sh

# Récupérer le code (ce depot entier, ou uniquement ce dossier)
git clone https://github.com/alexlacata/nvr.git ~/nvr-directory-src
cd ~/nvr-directory-src/nvr-directory

# Configurer le mot de passe et le domaine
cp .env.example .env
nano .env   # remplissez DIRECTORY_PASSWORD et DIRECTORY_DOMAIN, puis Ctrl+O, Entree, Ctrl+X

# Démarrer
docker compose up -d --build
```

Après quelques secondes (le temps que Caddy obtienne le certificat
HTTPS auprès de Let's Encrypt), ouvrez `https://<le domaine que vous avez
mis dans .env>` depuis n'importe quel appareil - vous devriez voir l'écran
de connexion.

## Mettre à jour

Comme pour le NVR :
```bash
cd ~/nvr-directory-src/nvr-directory
git pull
docker compose up -d --build
```
Vos données (la liste des NVR) vivent dans `nvr-directory/data/`, séparées
du code - une mise à jour ne les touche pas.

## Dépannage

- **Le certificat HTTPS ne se met pas en place** : vérifiez que le nom de
  domaine pointe bien vers l'adresse IP du VPS (`ping votre-domaine`
  depuis votre ordinateur doit répondre avec cette adresse) et que les
  ports 80 et 443 sont ouverts dans le pare-feu de l'hébergeur (souvent une
  page "Firewall"/"Pare-feu" dans son interface web). Les journaux :
  `docker compose logs -f caddy`.
- **"Trop de tentatives"** au moment de se connecter : anti-bruteforce
  volontaire (5 essais, puis blocage de 5 minutes pour cette adresse IP),
  pour cette page exposée directement sur internet. Attendez puis
  réessayez.
- **Je me reconnecte à chaque redémarrage du serveur** : les connexions
  ne sont pas conservées entre deux redémarrages du service (volontaire,
  pour garder ce service minimal) - aucune donnée n'est perdue, il suffit
  de se reconnecter.
