import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import asyncio
import os
import json
import aiohttp
import random
import string
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получаем токен напрямую из переменной окружения
TOKEN = os.getenv("TOKEN")

# API ключ для связи с плагином Minecraft (должен совпадать с ключом в конфиге плагина)
API_KEY = os.getenv("API_KEY", "YOUR_SECRET_API_KEY_CHANGE_THIS")

# Настройки API
API_BASE_URL = "http://localhost:8080/api"  # Измените на IP вашего сервера Minecraft
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot client
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Словарь для хранения кодов верификации
verification_codes = {}

# Асинхронная функция для отправки запросов к API плагина
async def send_api_request(endpoint, data):
    url = f"{API_BASE_URL}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=data, headers=HEADERS) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    try:
                        error_json = json.loads(error_text)
                        return {"error": error_json.get("error", "Неизвестная ошибка")}
                    except:
                        return {"error": f"HTTP ошибка {response.status}: {error_text}"}
        except aiohttp.ClientError as e:
            return {"error": f"Ошибка соединения: {str(e)}"}
        except Exception as e:
            return {"error": f"Непредвиденная ошибка: {str(e)}"}

# Класс модального окна для перевода денег
class TransferModal(Modal, title="Перевод монет"):
    receiver = TextInput(
        label="Получатель",
        placeholder="Введите ник игрока получателя",
        required=True,
    )
    
    amount = TextInput(
        label="Сумма",
        placeholder="Сколько монет перевести",
        required=True,
    )
    
    message = TextInput(
        label="Сообщение (необязательно)",
        placeholder="Добавьте сообщение к переводу",
        required=False,
        style=discord.TextStyle.paragraph,
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Валидация суммы
        try:
            amount_value = float(self.amount.value)
            if amount_value <= 0:
                await interaction.response.send_message("Сумма должна быть положительной!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Пожалуйста, введите корректную сумму!", ephemeral=True)
            return
        
        # Показать загрузку
        await interaction.response.defer(ephemeral=True)
        
        # Данные для запроса к API
        data = {
            "sender_discord_id": str(interaction.user.id),
            "receiver_name": self.receiver.value,
            "amount": amount_value,
            "description": self.message.value if self.message.value else "Перевод из Discord"
        }
        
        # Отправляем запрос к API плагина
        response = await send_api_request("transfer", data)
        
        if "error" in response:
            await interaction.followup.send(f"Ошибка: {response['error']}", ephemeral=True)
        else:
            new_balance = response.get("new_balance", 0)
            await interaction.followup.send(
                f"Перевод выполнен успешно!\n"
                f"Вы перевели {amount_value} монет игроку {self.receiver.value}.\n"
                f"Ваш новый баланс: {new_balance} монет.", 
                ephemeral=True
            )

# Команда для проверки баланса
@tree.command(name="balance", description="Проверить свой баланс")
async def balance_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # Данные для запроса к API
    data = {
        "discord_id": str(interaction.user.id)
    }
    
    # Отправляем запрос к API плагина
    response = await send_api_request("balance", data)
    
    if "error" in response:
        if "не привязан" in response["error"]:
            await interaction.followup.send(
                "Ваш Discord аккаунт не привязан к аккаунту Minecraft!\n"
                "Используйте команду `/link`, чтобы привязать аккаунты.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"Ошибка: {response['error']}", ephemeral=True)
    else:
        balance = response.get("balance", 0)
        embed = discord.Embed(
            title="Ваш баланс",
            description=f"У вас на счету: **{balance} монет**",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Экономическая система Minecraft-Discord")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

# Команда для перевода денег
@tree.command(name="transfer", description="Перевести монеты другому игроку")
async def transfer_command(interaction: discord.Interaction):
    # Отправляем модальное окно для ввода данных
    await interaction.response.send_modal(TransferModal())

# Команда для привязки аккаунта Discord к Minecraft
@tree.command(name="link", description="Привязать Discord аккаунт к аккаунту Minecraft")
async def link_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # Данные для запроса к API
    data = {
        "discord_id": str(interaction.user.id),
        "discord_username": interaction.user.display_name
    }
    
    # Отправляем запрос к API плагина для получения кода верификации
    response = await send_api_request("link", data)
    
    if "error" in response:
        await interaction.followup.send(f"Ошибка: {response['error']}", ephemeral=True)
        return
    
    # Получаем код верификации из ответа
    verification_code = response.get("verification_code")
    
    if not verification_code:
        await interaction.followup.send("Не удалось получить код верификации. Попробуйте позже.", ephemeral=True)
        return
    
    # Отправляем код пользователю
    embed = discord.Embed(
        title="Привязка аккаунта Minecraft",
        description=(
            f"Ваш код верификации: **{verification_code}**\n\n"
            f"Войдите на сервер Minecraft и введите команду:\n"
            f"```/setdiscord {verification_code}```\n"
            f"Код действителен в течение 5 минут."
        ),
        color=discord.Color.blue()
    )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

# Команда для просмотра топ игроков по балансу
@tree.command(name="top", description="Показать топ игроков по балансу")
async def top_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # Это эндпоинт нужно добавить в плагин для реализации данной команды
    response = await send_api_request("top", {"limit": 10})
    
    if "error" in response:
        await interaction.followup.send(f"Ошибка: {response['error']}")
        return
    
    players = response.get("players", [])
    
    if not players:
        await interaction.followup.send("Информация о балансах игроков недоступна.")
        return
    
    embed = discord.Embed(
        title="Топ игроков по балансу",
        color=discord.Color.gold()
    )
    
    for i, player in enumerate(players, 1):
        embed.add_field(
            name=f"{i}. {player['name']}",
            value=f"{player['balance']} монет",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@client.event
async def on_ready():
    print(f'Бот {client.user} запущен и готов к работе!')
    
    # Sync commands
    try:
        await tree.sync()
        print("Команды успешно синхронизированы")
    except Exception as e:
        print(f"Ошибка при синхронизации команд: {e}")

@client.event
async def on_error(event, *args, **kwargs):
    print(f"Произошла ошибка в событии {event}: {args}, {kwargs}")

@client.event 
async def on_application_command_error(interaction, error):
    print(f"Ошибка при выполнении команды: {error}")
    await interaction.response.send_message(f"Произошла ошибка: {error}", ephemeral=True)

# Проверка наличия токена
if not TOKEN:
    print("ОШИБКА: Токен бота не указан в переменных окружения!")
    print("Добавьте переменную TOKEN в .env файл или в настройки платформы")
    exit(1)

# Start the bot
if __name__ == "__main__":
    client.run(TOKEN) 
