[Read in Turkish (Türkçe Oku)](README_tr.md)

---
# IGXDOWN

This project is a Python bot that downloads Instagram video links sent via Telegram and sends the video back to the user. It is designed to be hosted on [Render](https://render.com/) using `Dockerfile` for its entire functionality.

**Bot Link:** [IGXDOWN Bot](https://t.me/igxdown_bot)

## Features

-   Downloads **all media (videos and photos)** from a single Instagram post.
-   Sends multiple media in a single, clean message group (`MediaGroup`).
-   Easy-to-use Telegram bot interface with **multi-language support** (TR/EN).
-   Manual language selection via the `/start` command.
-   Simple and reliable deployment on Render with `Dockerfile`.
-   Audio support for videos thanks to `ffmpeg`.
-   Optional `INSTAGRAM_SESSIONID` usage for advanced cases.

## How It Works

This bot connects to the Telegram API using the `python-telegram-bot` library. Video downloading and sending are managed by the `bot.py` script. The script uses `yt-dlp`, a popular and powerful command-line tool, by running it through the `subprocess` module.

The `ffmpeg` dependency, which is necessary for merging separate video and audio streams, is automatically installed via the `Dockerfile` in the project's root directory.

The bot runs continuously as a "Worker Service" on Render, listening for incoming messages from Telegram.

## Setup and Deployment (To Create Your Own Bot by Forking This Repository)

Follow these steps to run this bot with your own Telegram account on Render:

### 1. Prerequisites

1.  **Fork this Repository:** Fork this GitHub repository to your own account.
2.  **Get a Telegram Bot Token:**
    *   If you don't have a bot, talk to [BotFather](https://t.me/BotFather) on Telegram.
    *   Use the `/newbot` command to create a new bot and follow the instructions.
    *   Copy the **API token** that BotFather gives you. This token must be kept secret.

### 2. Deploying on Render

1.  **Create/Login to Your Render Account:** Go to [Render.com](https://render.com/). Signing in with your GitHub account will make it easier to access your repositories.
2.  **Create a New Service:**
    *   On the Render dashboard, click **"New +" > "Worker Service"**. This is the most suitable service type as the bot will run continuously in the background.
3.  **Connect Your Repository:**
    *   Connect your GitHub account to Render and select the repository you forked from the list, then click "Connect".
4.  **Configure the Service:**
    *   **Name:** Give your service a name (e.g., `igxdown-bot`).
    *   **Region:** Choose a region closest to you (e.g., `Frankfurt`).
    *   **Branch:** Select the `main` branch.
    *   **Runtime:** Render will automatically detect the `Dockerfile` in your repository. Make sure **"Docker"** is selected as the runtime. In this case, you do not need to fill in the "Build Command" and "Start Command" fields.
    *   **Instance Type:** You can start with the `Free` plan.
5.  **Add Environment Variables:**
    *   Go to the "Advanced" section and click "Add Environment Variable". Add the following variables:
        *   **`TELEGRAM_TOKEN`**: Paste the API token you got from BotFather.
        *   **`INSTAGRAM_SESSIONID`** (Optional): If you want to download private videos or bypass some access issues, you can add your Instagram `sessionid` here.
6.  **Deploy:**
    *   Click the "Create Worker Service" button.
    *   Render will pull the code from your GitHub repository, build an image using the `Dockerfile` (installing `ffmpeg` and Python dependencies in this step), and finally start your bot.
7.  **Check the Logs:**
    *   After the deployment is complete, you can monitor your bot's logs from the "Logs" tab in the Render dashboard. When you see messages like "Bot started...", your bot is running successfully.

## Notes for Developers

### Using `INSTAGRAM_SESSIONID` (Optional)

This bot can download most public videos without a `sessionid`. However, setting the `INSTAGRAM_SESSIONID` environment variable in Render can be useful in the following cases:
-   **Downloading from Private Accounts.**
-   **Videos that Require Login.**
-   **Bypassing Rate Limiting / Blocking Issues:** When anonymous requests are frequently restricted or blocked by Instagram.

If this environment variable is set, the bot will automatically pass this information to `yt-dlp` via a cookie file.

**How to get `INSTAGRAM_SESSIONID`?**
1.  Go to Instagram.com in your browser and log in to your account.
2.  Open the developer tools (usually F12).
3.  Navigate to the `Application` (Chrome/Edge) or `Storage` (Firefox) tab and find `Cookies` > `https://www.instagram.com`.
4.  Find the cookie named `sessionid` and copy its value.
5.  Add this value to your service's environment variables on Render with the name `INSTAGRAM_SESSIONID`.

## File Structure

-   `bot.py`: Contains the Python code for the main Telegram bot application.
-   `requirements.txt`: Lists the required Python libraries.
-   `Dockerfile`: Contains instructions to build the environment (Python + ffmpeg) where the application will run on Render.
-   `locales/`: Contains JSON files for multi-language support (`tr.json`, `en.json`).
-   `README.md`: This file (English).
-   `README_tr.md`: Turkish version of the README.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
