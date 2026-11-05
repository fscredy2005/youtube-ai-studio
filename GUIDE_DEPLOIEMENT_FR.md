# YouTube AI Studio — mise en ligne sans programmation

## Avant de commencer

Tu as besoin de deux comptes gratuits : [GitHub](https://github.com/) et [Streamlit Community Cloud](https://share.streamlit.io/). Aucun logiciel à installer sur Windows pour utiliser l'application en ligne.

## Étape 1 — Extraire le ZIP

Télécharge l'archive `youtube-ai-studio-online.zip`, puis clic droit sur Windows → **Extraire tout**. Tu obtiens un dossier contenant `app.py`, `requirements.txt`, `README.md`, les sous-dossiers `studio`, `tests` et `.streamlit`.

## Étape 2 — Créer le dépôt GitHub

1. Ouvre [github.com/new](https://github.com/new).
2. Nom du dépôt : `youtube-ai-studio`. Tu peux le configurer comme **Private** (recommandé si c'est juste pour toi).
3. Crée le dépôt sans ajouter de README automatique.
4. Clique **uploading an existing file** puis ajoute les fichiers et dossiers du ZIP extrait en conservant l'arborescence d'origine. Vérifie absolument la présence de `studio/youtube.py` et `.streamlit/config.toml`.
5. Termine par **Commit changes**.

Ne mets jamais de clé API dans le dépôt, même privé. Ne transfère pas de fichier `.env` contenant des secrets.

## Étape 3 — Mettre en ligne via Streamlit

1. Ouvre [share.streamlit.io](https://share.streamlit.io/).
2. Connecte ton compte GitHub et choisis **Create app**.
3. Sélectionne ton dépôt `youtube-ai-studio`, branche `main`, fichier `app.py`.
4. Clique **Deploy**.
5. Ton application sera disponible sur une adresse HTTPS finissant par `.streamlit.app`.

Les installations et ressources des services gratuits peuvent prendre du temps, et les offres peuvent évoluer.

## Étape 4 — Tester gratuitement

Ouvre ton application, colle une URL de vidéo YouTube publique et clique sur **Analyze video**.

Si l'extraction est bloquée par YouTube : ouvre **More options**, puis colle un transcript existant ou importe un fichier audio/vidéo que tu as le droit d'utiliser.

Le résumé gratuit extrait des passages importants : ce n'est pas un résumé rédigé par une IA générative.

## Étape 5 — Ajouter les vrais résumés IA (optionnel)

1. Crée une clé dans [Google AI Studio](https://aistudio.google.com/apikey), en vérifiant les quotas et conditions de facturation en vigueur.
2. Dans Streamlit Community Cloud, ouvre les paramètres de ton application → **Secrets**.
3. Ajoute :

   ```toml
   GEMINI_API_KEY = "TA_CLE_GEMINI"
   GEMINI_MODEL = "gemini-2.5-flash-lite"
   ```

4. Sauvegarde et redémarre si nécessaire. Les résumés génératifs et les réponses aux questions deviennent disponibles.

Attention : si ton application est publique, les visiteurs peuvent utiliser indirectement ton quota Gemini. Pour un usage personnel, limite les accès à l'application.

## Limitations importantes

- Les serveurs gratuits peuvent être mis en veille, saturés ou bloqués par YouTube.
- Les téléchargements de vidéos YouTube sont **désactivés par défaut** ; les exports TXT, SRT, Markdown et PDF sont actifs.
- La transcription Whisper sur un petit serveur gratuit peut être lente, voire échouer faute de mémoire.
- L'historique ne survit pas à la fermeture ou à la réinitialisation de la session.
- Le code a été testé sur ses composants Python, mais la mise en ligne effective n'est pas incluse dans l'archive.
