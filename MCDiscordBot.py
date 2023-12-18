TOKEN = None
SERVER_DIRECTORY = "./MINECRAFT/server"
SERVER_NAME = "Minecraft Server"
SERVER_SHELL = "run.bat"
SERVER_LOG = "logs/latest.log"
SERVER_PORT = 25565

import os
import re
import signal
import time
import subprocess

import asyncio

import mcrcon

import discord
from discord import app_commands

channel_id = 1185881826527559710

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client=client)
server_address = "localhost"
server_port = 25575
server_password = "minecraft"
last_execution_time = 0
process = None

# discord_token.txt からdiscord botのtokenを読み込む
TOKEN = open("discord_token.txt", "r").read()


@tree.command(name="hello", description="Hello, world!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.mention}!")


@tree.command(name="start", description="Starts the Minecraft server")
async def start_server(interaction: discord.Interaction):
    global last_execution_time
    global process
    channel = interaction.channel
    # 2分以内に実行された場合は、実行しない
    if time.time() - last_execution_time < 120:
        await interaction.response.send_message(
            "Please wait 2 minutes before starting the server again!"
        )
        return
    # if minecraft server is already running
    if is_server_running():
        await interaction.response.send_message("Minecraft server is already running!")
        return
    # Code to start the Minecraft server
    else:
        await interaction.response.send_message("Start Command Received!")
        sent_message = await channel.send("```fix\nStarting Minecraft server...\n```")
        last_execution_time = time.time()
        # Start the Minecraft server
        success = await start_process()
        if not success:
            await sent_message.edit(
                content="```arm\nMinecraft server failed to start!\n```"
            )
            return
        await sent_message.edit(content="```fix\nMinecraft server started!\n```")
        # Change presence to show server is running
        await client.change_presence(activity=discord.Game(name=SERVER_NAME))


async def start_process():
    global process
    # もし現在のディレクトリがサーバーのディレクトリでない場合は、移動する
    if os.getcwd() != SERVER_DIRECTORY:
        os.chdir(SERVER_DIRECTORY)
    # shell scriptを実行して、サーバーを起動する
    process = subprocess.Popen(
        SERVER_SHELL,
        shell=True,
    )
    # Wait for server to start
    start_time = time.time()
    while not is_server_running():
        if time.time() - start_time > 300:
            # kill the server process
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            return False
        await asyncio.sleep(1)
    return True


@tree.command(name="backup", description="Backs up the Minecraft server")
async def backup_server(interaction: discord.Interaction):
    # Code to backup the Minecraft server
    await interaction.response.send_message("Backup Command Received!")


@tree.command(name="stop", description="Stops the Minecraft server")
async def stop_server(interaction: discord.Interaction):
    # if minecraft server is already running
    if is_server_running():
        await interaction.response.send_message("Stop Command Received!")
        channel = interaction.channel
        sent_message = await channel.send("```fix\nStopping Minecraft server...\n```")
        # Code to stop the Minecraft server
        # use rcon to stop the server
        with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
            resp = mcr.command("stop")
            print(resp)
        # Wait for server to stop
        start_time = time.time()
        while is_server_running():
            if time.time() - start_time > 60:
                await sent_message.edit(
                    content="```arm\nMinecraft server failed to stop!\n```"
                )
                return
            await asyncio.sleep(1)
        # Change presence to show server is not running
        await client.change_presence(activity=discord.Game(name=""))
        await sent_message.edit(content="```fix\nMinecraft server stopped!\n```")
    else:
        await interaction.response.send_message("Minecraft server is not running!")


@tree.command(name="status", description="Checks the status of the Minecraft server")
async def status_server(interaction: discord.Interaction):
    if is_server_running():
        await interaction.response.send_message("Minecraft server is running!")
    else:
        await interaction.response.send_message("Minecraft server is not running!")


# Minecraft Server に接続しているプレイヤーの一覧を表示する
@tree.command(name="list", description="Lists the players on the Minecraft server")
async def list_server(interaction: discord.Interaction):
    if is_server_running():
        # 参加人数を確認する
        with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
            resp = mcr.command("list")
        resp = resp.split(" ")[1:]
        if len(resp) == 0:
            resp = "No"
        resp = f"```fix\n{resp} players are playing on the server.\n```"
        await interaction.response.send_message(resp)
    else:
        await interaction.response.send_message("Minecraft server is not running!")


# 管理者のみが実行できるdiscord bot終了コマンド
@tree.command(name="exit", description="Stops the Discord bot")
@app_commands.default_permissions(administrator=True)
async def exit_bot(interaction: discord.Interaction):
    await interaction.response.send_message("Exit Command Received!")
    await client.close()


# 管理者のみが実行できるsayコマンド
@tree.command(name="say", description="Says a message on the Minecraft server")
@app_commands.default_permissions(administrator=True)
async def say_server(interaction: discord.Interaction, message: str):
    if is_server_running():
        # メッセージをサーバーに送信する
        with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
            mcr.command(f"say {message}")
        await interaction.response.send_message("Message sent!")
    else:
        await interaction.response.send_message("Minecraft server is not running!")


# 管理者のみが実行できるサーバー操作コマンド
@tree.command(name="command", description="Sends a command to the Minecraft server")
@app_commands.default_permissions(administrator=True)
async def say_server(interaction: discord.Interaction, message: str):
    if is_server_running():
        # メッセージの先頭に/がない場合は、/を追加する
        if message[0] != "/":
            message = "/" + message
        # メッセージをサーバーに送信する
        with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
            mcr.command(f"{message}")
        await interaction.response.send_message("Message sent!")
    else:
        await interaction.response.send_message("Minecraft server is not running!")


# Minecraft Server に接続しているプレイヤーを監視して、0人になったら5分後にサーバーを停止する
# 定期的に自動実行され、プレイヤーがいる場合はタイマーをリセットする。
async def check_player():
    while True:
        print("Checking for players...")
        if is_server_running():
            # プレイヤーが存在しているかどうかを確認する
            with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
                resp = mcr.command("list")
            # プレイヤーが存在しない場合は、5分後にサーバーを停止する
            if re.search(r"0 of a max of 20 players online", resp):
                # サーバーにプレイヤーがいないことをdiscordに通知する
                channel = client.get_channel(channel_id)
                await channel.send(
                    "```txt\nNo players are playing on the server.\nIf no players join within 5 minutes, the server will be stopped.```"
                )
                await asyncio.sleep(300)
                with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
                    resp = mcr.command("list")
                # 5分後にもプレイヤーがいない場合は、サーバーを停止する
                if (
                    re.search(r"0 of a max of 20 players online", resp)
                    and is_server_running()
                ):
                    # サーバーを停止するコマンドを実行する
                    with mcrcon.MCRcon(
                        server_address, server_password, server_port
                    ) as mcr:
                        resp = mcr.command("stop")
                    # Wait for server to stop
                    start_time = time.time()
                    while is_server_running():
                        if time.time() - start_time > 60:
                            # one more try
                            with mcrcon.MCRcon(
                                server_address, server_password, server_port
                            ) as mcr:
                                resp = mcr.command("stop")
                            start_time = time.time()
                        await asyncio.sleep(5)
                    # Change presence to show server is not running
                    await client.change_presence(activity=discord.Game(name=""))
                    # サーバーが停止したことをdiscordに通知する
                    await channel.send("```fix\nMinecraft server stopped!\n```")
            else:
                # プレイヤーがいる場合は、5分後に再度確認する
                await asyncio.sleep(300)
        # 1分ごとに確認する
        await asyncio.sleep(60)


def is_server_running():
    # Code to check if the Minecraft server is running
    # マイクラサーバーがオンラインかどうかmcrconで確認する
    try:
        with mcrcon.MCRcon(server_address, server_password, server_port) as mcr:
            resp = mcr.command("list")
        return True
    except:
        return False


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user.name}")
    # Change presence to show server is not running
    await client.change_presence(activity=discord.Game(name=""))
    client.loop.create_task(check_player())


def main():
    # Discord Botを実行する
    client.run(TOKEN)


if __name__ == "__main__":
    main()
