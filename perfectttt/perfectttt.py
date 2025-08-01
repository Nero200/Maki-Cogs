import discord
import logging
import random
from redbot.core import commands

log = logging.getLogger("red.nero.perfectttt")

class PerfectTTT(commands.Cog):
    """
    Perfect Tic Tac Toe - An unbeatable version of Tic Tac Toe using the minimax algorithm
    """

    def __init__(self, bot):
        self.bot = bot
        self.ttt_games = {}

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def perttt(self, ctx, move=""):
        """Play Tic Tac Toe against a perfect AI that will never lose"""
        await self.ttt_new(ctx.author, ctx.channel)

    async def ttt_new(self, user, channel):
        """Create a new game"""
        self.ttt_games[user.id] = [" "] * 9
        # If AI goes first (randomly chosen 50% of the time), make optimal first move
        if random.choice([True, False]):
            self.ttt_games[user.id][4] = "o"  # AI takes center
            response = self._make_board(user)
            response += "I go first! Your move:"
        else:
            response = self._make_board(user)
            response += "Your move:"
        
        msg = await channel.send(response)
        await self._make_buttons(msg)

    async def ttt_move(self, user, message, move):
        """Process a player move"""
        log.debug(f"ttt_move:{user.id}")
        # Check user currently playing
        if user.id not in self.ttt_games:
            log.debug("New ttt game")
            return await self.ttt_new(user, message.channel)

        # Check spot is empty
        if self.ttt_games[user.id][move] == " ":
            self.ttt_games[user.id][move] = "x"
            log.debug(f"Player moved to {move}")
        else:
            log.debug(f"Invalid move: {move}")
            return None

        # Check winner
        check = self._do_checks(self.ttt_games[user.id])
        if check is not None:
            msg = "It's a draw!" if check == "draw" else f"{check[-1]} wins!"
            log.debug(msg)
            await message.edit(content=f"{self._make_board(user)}{msg}")
            del self.ttt_games[user.id]  # Clear game from memory
            return None
        log.debug("Check passed")

        # AI move using minimax (perfect play)
        board_state = self.ttt_games[user.id].copy()
        best_move = self._minimax_move(board_state)
        if best_move is not None:
            self.ttt_games[user.id][best_move] = "o"
            log.debug(f"AI moved to {best_move}")
        else:
            log.debug("AI couldn't find a move (shouldn't happen)")

        # Update board
        await message.edit(content=self._make_board(user))
        log.debug("Board updated")

        # Check winner again
        check = self._do_checks(self.ttt_games[user.id])
        if check is not None:
            msg = "It's a draw!" if check == "draw" else f"{check[-1]} wins!"
            log.debug(msg)
            await message.edit(content=f"{self._make_board(user)}{msg}")
            del self.ttt_games[user.id]  # Clear game from memory
        log.debug("Check passed")

    def _make_board(self, author):
        """Create a visual representation of the board"""
        return f"{author.mention}\n{self._table(self.ttt_games[author.id])}\n"

    async def _make_buttons(self, msg):
        """Add reaction buttons for moves"""
        await msg.add_reaction("\u2196")  # 0 tl
        await msg.add_reaction("\u2B06")  # 1 t
        await msg.add_reaction("\u2197")  # 2 tr
        await msg.add_reaction("\u2B05")  # 3 l
        await msg.add_reaction("\u23FA")  # 4 mid
        await msg.add_reaction("\u27A1")  # 5 r
        await msg.add_reaction("\u2199")  # 6 bl
        await msg.add_reaction("\u2B07")  # 7 b
        await msg.add_reaction("\u2198")  # 8 br

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle reaction-based moves"""
        if user.bot:
            return
        if reaction.message.guild is None:
            return
        if reaction.message.author != self.bot.user:
            return
        game_session = self.ttt_games.get(user.id, None)
        if game_session is None:
            return
        move = self._decode_move(str(reaction.emoji))
        if move is None:
            return
        await self.ttt_move(user, reaction.message, move)

    @staticmethod
    def _decode_move(emoji):
        """Convert emoji to board position"""
        dict = {
            "\u2196": 0,  # top-left
            "\u2B06": 1,  # top
            "\u2197": 2,  # top-right
            "\u2B05": 3,  # left
            "\u23FA": 4,  # middle
            "\u27A1": 5,  # right
            "\u2199": 6,  # bottom-left
            "\u2B07": 7,  # bottom
            "\u2198": 8,  # bottom-right
        }
        return dict[emoji] if emoji in dict else None

    @staticmethod
    def _table(xo):
        """Format the board with emojis"""
        return (
            (("%s%s%s\n" * 3) % tuple(xo))
            .replace("o", ":o2:")
            .replace("x", ":regional_indicator_x:")
            .replace(" ", ":white_large_square:")
        )

    def _do_checks(self, board):
        """Check if the game is over (win or draw)"""
        # Check for X win
        if self._check_win(board, "x"):
            return "win X"
        # Check for O win
        if self._check_win(board, "o"):
            return "win O"
        # Check for draw
        if self._check_draw(board):
            return "draw"
        return None

    @staticmethod
    def _check_win(board, player):
        """Check if the given player has won"""
        # Check rows
        for i in range(0, 9, 3):
            if board[i] == board[i+1] == board[i+2] == player:
                return True
        # Check columns
        for i in range(3):
            if board[i] == board[i+3] == board[i+6] == player:
                return True
        # Check diagonals
        if board[0] == board[4] == board[8] == player:
            return True
        if board[2] == board[4] == board[6] == player:
            return True
        return False

    @staticmethod
    def _check_draw(board):
        """Check if the game is a draw"""
        return " " not in board

    def _minimax_move(self, board):
        """Find the best move using the minimax algorithm"""
        # If board is empty or has only one move, pick center or corner
        empty_count = board.count(" ")
        if empty_count == 9:
            return 4  # Always take center first
        if empty_count == 8:
            if board[4] == " ":
                return 4  # Take center if player didn't
            else:
                return random.choice([0, 2, 6, 8])  # Take a corner
        
        # Use minimax to find the best move
        best_score = float('-inf')
        best_move = None
        
        for i in range(9):
            if board[i] == " ":
                board[i] = "o"  # Try this move for AI
                score = self._minimax(board, 0, False)
                board[i] = " "  # Undo the move
                
                if score > best_score:
                    best_score = score
                    best_move = i
        
        return best_move

    def _minimax(self, board, depth, is_maximizing):
        """
        Minimax algorithm implementation
        - board: current board state
        - depth: current depth in the search tree
        - is_maximizing: whether current player is maximizing (AI) or minimizing (human)
        """
        # Check terminal states
        if self._check_win(board, "o"):
            return 10 - depth  # AI wins (higher score for quicker wins)
        if self._check_win(board, "x"):
            return depth - 10  # Human wins (lower score)
        if self._check_draw(board):
            return 0  # Draw
            
        if is_maximizing:
            # AI's turn (maximizing)
            best_score = float('-inf')
            for i in range(9):
                if board[i] == " ":
                    board[i] = "o"
                    score = self._minimax(board, depth + 1, False)
                    board[i] = " "
                    best_score = max(score, best_score)
            return best_score
        else:
            # Human's turn (minimizing)
            best_score = float('inf')
            for i in range(9):
                if board[i] == " ":
                    board[i] = "x"
                    score = self._minimax(board, depth + 1, True)
                    board[i] = " "
                    best_score = min(score, best_score)
            return best_score