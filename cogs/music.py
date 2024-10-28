# -*- coding: utf-8 -*-

"""


A simple music bot written in discord.py using youtube-dl(THIS FORK ACTUALLY WORKS!!!!!)

Though it's a simple example, music bots are complex and require much time and knowledge until they work perfectly.
Use this as an example or a base for your own bot and extend it as you want. If there are any bugs, please let me know.

Requirements:

Python 3.5+
pip install -U pynacl py-cord[voice] yt-dlp

You also need FFmpeg in your PATH environment variable or the FFmpeg.exe binary in your bot's directory on Windows.
Submit issues and PRS here https://github.com/JeffreyGoe/MusicBot
"""

import asyncio
import functools
import itertools
import logging
import math
import random
import os
import discord
from discord.ext import commands
import sys
import yt_dlp as youtube_dl
from async_timeout import timeout
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MusicBot')

# Silence useless bug reports messages
youtube_dl.utils.bug_reports_message = lambda: ""


class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        "format": "bestaudio/best",
        "extractaudio": True,
        "audioformat": "mp3",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
    }

    FFMPEG_OPTIONS = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn",
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(
        self,
        ctx: discord.ApplicationContext,
        source: discord.FFmpegPCMAudio,
        *,
        data: dict,
        volume: float = 0.5,
    ):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get("uploader")
        self.uploader_url = data.get("uploader_url")
        date = data.get("upload_date")
        self.upload_date = date[6:8] + "." + date[4:6] + "." + date[0:4]
        self.title = data.get("title")
        self.thumbnail = data.get("thumbnail")
        self.description = data.get("description")
        self.duration = self.parse_duration(int(data.get("duration")))
        self.tags = data.get("tags")
        self.url = data.get("webpage_url")
        self.views = data.get("view_count")
        self.likes = data.get("like_count")
        self.dislikes = data.get("dislike_count")
        self.stream_url = data.get("url")

    def __str__(self):
        return "**{0.title}** by **{0.uploader}**".format(self)

    @classmethod
    async def create_source(
        cls,
        ctx: discord.ApplicationContext,
        search: str,
        *,
        loop: asyncio.BaseEventLoop = None,
    ):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(
            cls.ytdl.extract_info, search, download=False, process=False
        )
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError("Couldn't find anything that matches `{}`".format(search))

        if "entries" not in data:
            process_info = data
        else:
            process_info = None
            for entry in data["entries"]:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError(
                    "Couldn't find anything that matches `{}`".format(search)
                )

        webpage_url = process_info["webpage_url"]
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError("Couldn't fetch `{}`".format(webpage_url))

        if "entries" not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info["entries"].pop(0)
                except IndexError:
                    raise YTDLError(
                        "Couldn't retrieve any matches for `{}`".format(webpage_url)
                    )

        try:
            cls = cls(
                ctx,
                discord.FFmpegPCMAudio(info["url"], **cls.FFMPEG_OPTIONS),
                data=info,
            )
        except discord.ClientException:
            raise YTDLError(
                "FFmpegPCMAudio Subprocess failed to be created. Is one already running?"
            )
        return cls

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        output = []
        if days > 0:
            output.append("{} days".format(days))
        if hours > 0:
            output.append("{} hours".format(hours))
        if minutes > 0:
            output.append("{} minutes".format(minutes))
        if seconds > 0:
            output.append("{} seconds".format(seconds))

        return ", ".join(output)


class Song:
    __slots__ = ("source", "requester")

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def _format_views(self, num):
        if abs(num) >= 1_000_000_000:
            return f"{num / 1_000_000_000:.1f}B"
        elif abs(num) >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return str(num)

    def create_embed(self):
        embed = (
            discord.Embed(
                title="Now playing",
                description="```md\n{0.source.title}\n```".format(self),
                color=discord.Color.blurple(),
            )
            .add_field(name="Duration", value=self.source.duration)
            .add_field(name="Requested by", value=self.requester.mention)
            .add_field(
                name="Uploader",
                value="[{0.source.uploader}]({0.source.uploader_url})".format(self),
            )
            .add_field(name="Views", value=self._format_views(self.source.views))
            .add_field(name="Upload Date", value=self.source.upload_date)
            .add_field(name="URL", value="[Click]({0.source.url})".format(self))
            .set_thumbnail(url=self.source.thumbnail)
        )

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: discord.ApplicationContext):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()
        self.NowPlayingMessage = None
        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value
        try:
            self.voice_client.source.volume = float(value) / 100.0
        except Exception as e:
            pass

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    random_timeout = random.randint(20, 300)
                    async with timeout(random_timeout):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return False

            self.current.source.volume = self._volume
            try:
                self.voice.play(self.current.source, after=self.play_next_song)
            except Exception as e:
                print("Error occured when trying to play song {}".format(e))

            # if self.NowPlayingMessage:
            # await self.NowPlayingMessage.delete()

            self.NowPlayingMessage = await self.current.source.channel.send(
                embed=self.current.create_embed()
            )

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            self.voice.stop()
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    music_group = discord.commands.SlashCommandGroup("music", "Music bot commands.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: discord.ApplicationContext):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: discord.ApplicationContext):
        if not ctx.guild:
            raise commands.NoPrivateMessage(
                "This command can't be used in DM channels."
            )

        return True

    async def cog_before_invoke(self, ctx: discord.ApplicationContext):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(
        self, ctx: discord.ApplicationContext, error: commands.CommandError
    ):
        logging.error("An error occurred: {}".format(str(error)))
        await ctx.respond("An error occurred: {}".format(str(error)))
    
    async def play_meow(self, ctx, voice_client):
        """Play a random meow sound from YouTube."""
        meows = ["https://www.youtube.com/watch?v=uLB1ZeRgl_k",
                "https://www.youtube.com/watch?v=WsTb8HYZd-U",
                ]
        meow_url = random.choice(meows)
        try:
            source = await YTDLSource.create_source(ctx, meow_url, loop=self.bot.loop)
            voice_client.play(source, after=lambda _: print('Meow played'))
            
            # Wait for the meow to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"An error occurred while playing meow: {e}")

    @music_group.command(name="join", invoke_without_subcommand=True)
    async def _join(self, ctx: discord.ApplicationContext):
        """Joins a voice channel."""
        logger.debug(f"Join command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
        else:
            ctx.voice_state.voice = await destination.connect()
        
        # Play meow sound effect
        await self.play_meow(ctx, ctx.voice_state.voice)

    @music_group.command(name="summon")
    async def _summon(self, ctx: discord.ApplicationContext, *, channel: discord.VoiceChannel = None):
        """Summons the bot to a voice channel."""
        logger.debug(f"Summon command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not channel and not ctx.author.voice:
            raise VoiceError("You are neither connected to a voice channel nor specified a channel to join.")

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @music_group.command(name="leave", aliases=["disconnect"])
    async def _leave(self, ctx: discord.ApplicationContext):
        """Clears the queue and leaves the voice channel."""
        logger.debug(f"Leave command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not ctx.voice_state.voice:
            return await ctx.respond("Not connected to any voice channel.", ephemeral=True)

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @music_group.command(name="volume")
    async def _volume(self, ctx: discord.ApplicationContext, *, volume: int):
        """Sets the volume of the player."""
        logger.debug(f"Volume command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id}). New volume: {volume}")
        
        if not ctx.voice_state.is_playing:
            return await ctx.respond("Nothing being played at the moment.", ephemeral=True)

        if 0 > volume > 100:
            return await ctx.respond("Volume must be between 0 and 100", ephemeral=True)

        ctx.voice_state.volume = volume / 100
        await ctx.respond(f"Volume set to {volume}%")

    @music_group.command(name="now", aliases=["current", "playing"])
    async def _now(self, ctx: discord.ApplicationContext):
        """Displays the currently playing song."""
        logger.debug(f"Now Playing command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        await ctx.respond(embed=ctx.voice_state.current.create_embed(), ephemeral=True)

    @music_group.command(name="pause")
    async def _pause(self, ctx: discord.ApplicationContext):
        """Pauses the currently playing song."""
        logger.debug(f"Pause command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.respond("⏸️")

    @music_group.command(name="resume")
    async def _resume(self, ctx: discord.ApplicationContext):
        """Resumes a currently paused song."""
        logger.debug(f"Resume command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.respond("▶️")

    @music_group.command(name="stop")
    async def _stop(self, ctx: discord.ApplicationContext):
        """Stops playing song and clears the queue."""
        logger.debug(f"Stop command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        ctx.voice_state.songs.clear()

        if not ctx.voice_state.voice:
            return await ctx.respond("Not connected to any voice channel.", ephemeral=True)

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        await ctx.respond("Stopping bot")

    @music_group.command(name="skip")
    async def _skip(self, ctx: discord.ApplicationContext):
        """Skip a song."""
        logger.debug(f"Skip command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not ctx.voice_state.is_playing:
            return await ctx.respond("Not playing any music right now...", ephemeral=True)

        await ctx.respond("Skipping...")
        ctx.voice_state.skip()

    @music_group.command(name="queue")
    async def _queue(self, ctx: discord.ApplicationContext, *, page: int = 1):
        """Shows the player's queue."""
        logger.debug(f"Queue command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id}). Page requested: {page}")
        
        if len(ctx.voice_state.songs) == 0:
            return await ctx.respond("Empty queue.")

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ""
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += f"`{i + 1}.` [**{song.source.title}**]({song.source.url})\n"

        embed = discord.Embed(description=f"**{len(ctx.voice_state.songs)} tracks:**\n\n{queue}")
        embed.set_footer(text=f"Viewing page {page}/{pages}")
        await ctx.respond(embed=embed)

    @music_group.command(name="shuffle")
    async def _shuffle(self, ctx: discord.ApplicationContext):
        """Shuffles the queue."""
        logger.debug(f"Shuffle command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if len(ctx.voice_state.songs) == 0:
            return await ctx.respond("Empty queue.", ephemeral=True)

        ctx.voice_state.songs.shuffle()
        await ctx.respond("Shuffled. 🔀")

    @music_group.command(name="remove")
    async def _remove(self, ctx: discord.ApplicationContext, index: int):
        """Removes a song from the queue at a given index."""
        logger.debug(f"Remove command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id}). Index to remove: {index}")
        
        if len(ctx.voice_state.songs) == 0:
            return await ctx.respond("Empty queue.", ephemeral=True)

        ctx.voice_state.songs.remove(index - 1)
        await ctx.respond(f"Removing song at index {index}")

    @music_group.command(name="loop")
    async def _loop(self, ctx: discord.ApplicationContext):
        """Loops the currently playing song."""
        logger.debug(f"Loop command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id})")
        
        if not ctx.voice_state.is_playing:
            return await ctx.respond("Nothing being played at the moment.")

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.respond("Looping 🔁" if ctx.voice_state.loop else "Unlooping 🔁")

    @music_group.command(name="play", description="plays a song")
    async def _play(self, ctx: discord.ApplicationContext, *, search: str):
        """Plays a song."""
        logger.debug(f"Play command invoked by {ctx.author} (ID: {ctx.author.id}) in server {ctx.guild.name} (ID: {ctx.guild.id}), channel {ctx.channel.name} (ID: {ctx.channel.id}). Search query: {search}")
        
        # defer
        await ctx.defer()
        
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        if ctx.voice_state.audio_player.done():
            ctx.voice_state.audio_player = self.bot.loop.create_task(ctx.voice_state.audio_player_task())

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.followup.send(f"An error occurred while processing this request: {str(e)}")
                logger.error(f"YTDLError in Play command: {str(e)}")
            else:
                song = Song(source)
                await ctx.voice_state.songs.put(song)
                await ctx.followup.send(f"{str(source)}")

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: discord.ApplicationContext):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to any voice channel.")

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError("Bot is already in a voice channel.")


def setup(bot):
    bot.add_cog(Music(bot))
