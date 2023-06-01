import discord
from discord.ext import commands
from redbot.core import Config, commands, checks
from redbot.core.utils import embed
from ifttt_webhook import IftttWebhook

class Post(commands.Cog):
    """My custom cog."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=10519211991920851915141567154, force_registration=True)

        default_global = {
            "discordchannel": "channel",
            "iftttkey": "thisisthekey",
            "iftttfacebook": "facebook-url",
            "ifttttumblr": "tumblr-url",
            "iftttreddit": "reddit-url",
            "iftttblogger": "blogger-url",
            "ifttttwitter": "twitter-url",
            "iftttwordpress": "wordpress-url"
        }

        default_user = {
            "posttitle": "UNSET",
            "postbody": "UNSET",
            "posttwitter": "no",
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_global)
        self.config.register_user(**default_user)

    @commands.group()
    @commands.has_role("Creators")
    async def post(self,ctx):
        """Post messages to social media."""

    @post.command()
    async def twitter(self, ctx):
        """Post message to twitter."""
        post_twitter = await self.config.user(ctx.author).posttwitter()
        twitter_post_true = "yes"
        twitter_post_false = "no"
        if post_twitter == twitter_post_true:
            embed = discord.Embed(title = "Post to Twitter:", description = "Webhook post sent.", color = discord.Color.green())
            await ctx.send(embed=embed)
        elif post_twitter == twitter_post_false:
            embed = discord.Embed(title = "Post twitterconfig ERROR!", description = "Post twitterconfig currently disabled.\nPlease use [.post twitterconfig yes] if you wish to post to twitter.", color = discord.Color.red())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title = "Post twitterconfig ERROR!", description = "Twitterconfig is not set up properly.\nPlease use [.post twitterconfig yes] if you wish to post to twitter.", color = discord.Color.yellow())
            await ctx.send(embed=embed)
    @post.command()
    async def title(self, ctx, post_title):
        """Store the post title."""
        await self.config.user(ctx.author).posttitle.set(post_title)
        embed = discord.Embed(title = "The post title is now set to:", description = post_title, color = discord.Color.green())
        await ctx.send(embed=embed)

    @post.command()
    async def body(self, ctx, post_body):
        """Store the post body."""
        await self.config.user(ctx.author).postbody.set(post_body)
        embed = discord.Embed(title = "The post body is now set to:", description = post_body, color = discord.Color.green())
        await ctx.send(embed=embed)

    @post.command()
    async def twitterconfig(self, ctx, post_twitter):
        """Are we posting to twitter? (yes or no)"""
        await self.config.user(ctx.author).posttwitter.set(post_twitter)
        if post_twitter == "yes":
            embed = discord.Embed(title = "Post TwitterConfig:", description = "Post TwitterConfig set to: " + post_twitter, color = discord.Color.green())
            await ctx.send(embed=embed)
        elif post_twitter == "no":
            embed = discord.Embed(title = "Post TwitterConfig:", description = "Post TwitterConfig set to: " + post_twitter, color = discord.Color.red())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title = "Post TwitterConfig:", description = "Post TwitterConfig incorrectly set to: " + post_twitter + ".\nPlease use the command [.post twitterconfig (yes/no)] to set twitterconfig.", color = discord.Color.yellow())
            await ctx.send(embed=embed)


    @post.command()
    async def submit(self, ctx):
        """Post content to social media."""
        post_twitter = await self.config.user(ctx.author).posttwitter()
        twitter_post_true = "yes"
        twitter_post_false = "no"
        if post_twitter == twitter_post_false:
            #post to discord
            post_channel = await self.config.guild(ctx.guild).discordchannel()
            channel = self.bot.get_channel(int(post_channel))
            post_title = await self.config.user(ctx.author).posttitle()
            post_body = await self.config.user(ctx.author).postbody()
            embed = discord.Embed(title = post_title, description = post_body, color = discord.Color.blue())
            await channel.send(embed=embed)
            #facebook key
            facebook_key = await self.config.guild(ctx.guild).iftttfacebook()
            #ifttt key
            ifttt_key = await self.config.guild(ctx.guild).iftttkey()
            #tumblr key
            tumblr_key = await self.config.guild(ctx.guild).ifttttumblr()
            #reddit key
            reddit_key = await self.config.guild(ctx.guild).iftttreddit()
            #ifttt setup
            ifttt = IftttWebhook(ifttt_key)
            #post to facebook
            ifttt.trigger(facebook_key, value1=post_title, value2=post_body, value3='none')
            #post to tumblr
            ifttt.trigger(tumblr_key, value1=post_title, value2=post_body, value3='none')
            #post to reddit
            ifttt.trigger(reddit_key, value1=post_title, value2=post_body, value3='none')
            #notify that post is complete
            embed = discord.Embed(title = "Post Submission:", description = "Webhook posts sent.", color = discord.Color.green())
            await ctx.send(embed=embed)
        elif post_twitter == twitter_post_true:
            embed = discord.Embed(title = "Post Submission ERROR!", description = "Post twitterconfig currently enabled.\nPlease use [.post twitterconfig no] to disable twitter and submit post.", color = discord.Color.red())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title = "Post Submission ERROR!", description = "Twitterconfig is not set up properly.\nPlease use [.post twitterconfig no] to disable twitter and submit post.", color = discord.Color.yellow())
            await ctx.send(embed=embed)

    @post.command()
    async def preview(self, ctx):
        """This is the post preview."""
        post_title = await self.config.user(ctx.author).posttitle()
        post_body = await self.config.user(ctx.author).postbody()
        post_twitter = await self.config.user(ctx.author).posttwitter()
        twitter_post_true = "yes"
        twitter_post_false = "no"
        post_twitter_signature = "We talk about this kind of stuff all the time on our Discord server. Stop by and say hi!  biblechanges mandelaeffect QuantumEffect amoseffect supernaturalbiblechanges prophecy BibleProphecy"
        post_twitter_count = str(len(post_title + post_body + post_twitter_signature)+29)
        if post_twitter == twitter_post_true:
            embed = discord.Embed(title = post_title, description = post_body + "\n\nTwitter post: " + post_twitter + "\nTwitter count: " + post_twitter_count, color = discord.Color.green())
            await ctx.send(embed=embed)
        elif post_twitter == twitter_post_false:
            embed = discord.Embed(title = post_title, description = post_body + "\n\nTwitter post: " + post_twitter, color = discord.Color.red())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title = post_title, description = post_body + "\n\nTwitter post: twitterconfig is not set up properly.\nPlease use [.post twitterconfig (yes/no)] to configure this setting depending on if you wish to post to twitter or not.", color = discord.Color.yellow())
            await ctx.send(embed=embed)

    @post.group(name="config", pass_context=True) #nested-group
    @commands.has_role("Bot-Dev")
    async def config(self, ctx):
        """Social feed settings."""

    @config.command(name="channel_api", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def channel_api(self, ctx, post_channel): 
        """Store which channel to post on Discord."""
        await self.config.guild(ctx.guild).discordchannel.set(post_channel)
        embed = discord.Embed(title = "Post Config Discord", description = "Discord Channel Set.", color = discord.Color.green())
        await ctx.send(embed=embed)

    @config.command(name="ifttt_api", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def ifttt_api(self, ctx, ifttt_key): 
        """Store the IFTTT Facebook Configuragion KEY."""
        await self.config.guild(ctx.guild).iftttkey.set(ifttt_key)
        embed = discord.Embed(title = "Post Config IFTTT", description = "IFTTT Configuration Set.", color = discord.Color.green())
        await ctx.send(embed=embed)

    @config.command(name="facebook_api", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def facebook_api(self, ctx, facebook_key): 
        """Store the IFTTT Facebook Configuragion KEY."""
        await self.config.guild(ctx.guild).iftttfacebook.set(facebook_key)
        embed = discord.Embed(title = "Post Config Facebook", description = "Facebook Configuration Set.", color = discord.Color.green())
        await ctx.send(embed=embed)
        
    @config.command(name="tumblr_api", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def tumblr_api(self, ctx, tumblr_key): 
        """Store the IFTTT Tumblr Configuragion KEY."""
        await self.config.guild(ctx.guild).ifttttumblr.set(tumblr_key)
        embed = discord.Embed(title = "Post Config Tumblr", description = "Tumblr Configuration Set.", color = discord.Color.green())
        await ctx.send(embed=embed)
        
    @config.command(name="reddit_api", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def reddit_api(self, ctx, reddit_key): 
        """Store the IFTTT Reddit Configuragion KEY."""
        await self.config.guild(ctx.guild).iftttreddit.set(reddit_key)
        embed = discord.Embed(title = "Post Config Reddit", description = "Reddit Configuration Set.", color = discord.Color.green())
        await ctx.send(embed=embed)

    @post.group(name="test", pass_context=True) #nested-group
    @commands.has_role("Bot-Dev")
    async def test(self, ctx):
        """Test out the social feeds."""

    @test.command(name="discord", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def discord(self, ctx): 
        """Post to Discord."""
        post_channel = await self.config.guild(ctx.guild).discordchannel()
        channel = self.bot.get_channel(int(post_channel))
        post_title = await self.config.user(ctx.author).posttitle()
        post_body = await self.config.user(ctx.author).postbody()
        embed = discord.Embed(title = post_title, description = post_body, color = discord.Color.blue())
        await channel.send(embed=embed)
        embed = discord.Embed(title = "Post Test Discord", description = "Test post sent.", color = discord.Color.green())
        await ctx.send(embed=embed)

    @test.command(name="facebook", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def facebook(self, ctx): 
        """Post to Facebook."""
        post_title = await self.config.user(ctx.author).posttitle()
        post_body = await self.config.user(ctx.author).postbody()
        ifttt_key = await self.config.guild(ctx.guild).iftttkey()
        facebook_key = await self.config.guild(ctx.guild).iftttfacebook()
        ifttt = IftttWebhook(ifttt_key)
        ifttt.trigger(facebook_key, value1=post_title, value2=post_body, value3='none')
        embed = discord.Embed(title = "Post Test Facebook", description = "Test post sent.", color = discord.Color.green())
        await ctx.send(embed=embed)
        
    @test.command(name="tumblr", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def tumblr(self, ctx): 
        """Post to Tumblr."""
        post_title = await self.config.user(ctx.author).posttitle()
        post_body = await self.config.user(ctx.author).postbody()
        ifttt_key = await self.config.guild(ctx.guild).iftttkey()
        tumblr_key = await self.config.guild(ctx.guild).ifttttumblr()
        ifttt = IftttWebhook(ifttt_key)
        ifttt.trigger(tumblr_key, value1=post_title, value2=post_body, value3='none')
        embed = discord.Embed(title = "Post Test Tumblr", description = "Test post sent.", color = discord.Color.green())
        await ctx.send(embed=embed)
        
    @test.command(name="reddit", pass_context=True) #nested-group command
    @commands.has_role("Bot-Dev")
    async def reddit(self, ctx): 
        """Post to Reddit."""
        post_title = await self.config.user(ctx.author).posttitle()
        post_body = await self.config.user(ctx.author).postbody()
        ifttt_key = await self.config.guild(ctx.guild).iftttkey()
        reddit_key = await self.config.guild(ctx.guild).iftttreddit()
        ifttt = IftttWebhook(ifttt_key)
        ifttt.trigger(reddit_key, value1=post_title, value2=post_body, value3='none')
        embed = discord.Embed(title = "Post Test Reddit", description = "Test post sent.", color = discord.Color.green())
        await ctx.send(embed=embed)
