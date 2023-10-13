import discord_token
import requests, urllib

def get_discord_nickname(discord_username=None):

    if discord_username == "None" or discord_username == "":
        return "000000000000000000"

    if "#" in discord_username:
        (username, discriminator) = discord_username.split("#")
        encoded_name = urllib.parse.quote(username)
    else:
        encoded_name = urllib.parse.quote(discord_username)

    GUILD_ID = discord_token.DISCORD_GUILD_ID
    TOKEN = discord_token.TOKEN

    headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
    url = f'https://discord.com/api/guilds/{GUILD_ID}/members/search?limit=1&query={encoded_name}'
    results = requests.get(url,headers=headers)

    if results.json()[0]['nick'] == None:
        return results.json()[0]['user']['global_name']
    else:
        return results.json()[0]['nick']

username = ""
nickname = get_discord_nickname(username)

print(nickname)