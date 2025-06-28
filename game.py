import pygame
import random
import sys
import time

# --- User-Provided Backend Logic (GUI-Agnostic) ---

class CoupError(Exception):
    """Base exception for Coup"""
    message = "An error has occured"
    def __init__(self, message=None):
        if message:
            self.message = message
        super(CoupError, self).__init__(self.message)

class NotEnoughCoins(CoupError):
    message = "Not enough coins"
class TargetRequired(CoupError):
    message = "Target required"
class InvalidTarget(CoupError):
    message = "Invalid target"
class ActionNotAllowed(CoupError):
    message = "Action not allowed"
class BlockOnly(CoupError):
    message = "This card can only be used for blocking"

class Action:
    name = ""
    description = ""
    blockable_by = []
    has_target = False
    coins_needed = 0
    character = None

    def play(self, player, target=None):
        return True, "Success"

class Income(Action):
    name = "Income"
    def play(self, player, target=None):
        player.coins += 1
        return True, "Success"

class ForeignAid(Action):
    name = "Foreign Aid"
    blockable_by = ['Duke']
    def play(self, player, target=None):
        player.coins += 2
        return True, "Success"

class Coup(Action):
    name = "Coup"
    has_target = True
    coins_needed = 7
    def play(self, player, target=None):
        if player.coins < self.coins_needed: raise NotEnoughCoins()
        if not target: raise TargetRequired()
        player.coins -= self.coins_needed
        # Influence loss is handled by the controller
        return True, "Success"

class Tax(Action):
    name = "Tax"
    character = 'Duke'
    def play(self, player, target=None):
        player.coins += 3
        return True, "Success"

class Steal(Action):
    name = "Steal"
    character = 'Captain'
    blockable_by = ['Captain', 'Ambassador']
    has_target = True
    def play(self, player, target=None):
        if not target: raise TargetRequired()
        stolen = min(2, target.coins)
        target.coins -= stolen
        player.coins += stolen
        return True, f"Stole {stolen} coins"

class Contessa(Action):
    name = "Contessa"
    character = 'Contessa'
    def play(self, player, target=None):
        raise BlockOnly()

class Assassinate(Action):
    name = "Assassinate"
    character = 'Assassin'
    blockable_by = ['Contessa']
    has_target = True
    coins_needed = 3  # <-- ADD THIS LINE
    can_be_bluffed = True
    def play(self, player, target=None):
        player.coins -= self.coins_needed
        return True, "Success"

class Exchange(Action):
    name = "Exchange"
    character = 'Ambassador'
    # This action blocks 'Steal' but is not blockable itself
    def play(self, player, target=None):
        # Logic for this is special and handled by the controller
        return True, "Success"

# --- Game State Singleton ---
class GameState:
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GameState, cls).__new__(cls)
        return cls._instance
    
    def initialize(self):
        self.players = []
        self.actions = {
            'Income': Income(), 'Foreign Aid': ForeignAid(), 'Coup': Coup(),
            'Tax': Tax(), 'Steal': Steal(), 'Assassinate': Assassinate(),
            'Exchange': Exchange()
        }
        self.cards_available = ['Duke', 'Captain', 'Assassin', 'Ambassador', 'Contessa']
        self.deck = self.cards_available * 3
        random.shuffle(self.deck)
        self.revealed_cards = []

    def draw_card(self):
        if not self.deck: return None
        return self.deck.pop()

    def add_to_deck(self, card_name):
        self.deck.append(card_name)
        random.shuffle(self.deck)

# --- Player Class ---
class Player:
    def __init__(self, player_id, name):
        self.id = player_id
        self.name = name
        self.coins = 2
        self.influence = [GameState().draw_card(), GameState().draw_card()]
        self.is_out = False

    def lose_influence(self, card_name):
        if card_name in self.influence:
            self.influence.remove(card_name)
            GameState().revealed_cards.append(card_name)
            if not self.influence:
                self.is_out = True
        else:
            # This case can happen if a player must lose influence but the card name is wrong.
            # A robust implementation would handle this, for now we lose the first available.
            if self.influence:
                 lost_card = self.influence.pop(0)
                 GameState().revealed_cards.append(lost_card)
                 if not self.influence:
                    self.is_out = True


    def has_card(self, card_name):
        return card_name in self.influence

# --- Pygame GUI and Controller ---

class GameController:
    """Manages game flow, state transitions, and player interactions."""
    def __init__(self, num_players=4):
        names = ["Leo", "Mikey", "Raph", "Donnie"]
        GameState().initialize()
        self.players = [Player(i, names[i]) for i in range(num_players)]
        GameState().players = self.players
        
        self.current_player_idx = 0
        self.state = 'INITIAL_REVEAL'
        self.reveal_turns_taken = 0
        self.cards_revealed_this_turn = False
        self.message = ""
        
        self.action = None
        self.action_player = None
        self.target_player = None
        self.potential_responders = []
        self.blocker = None
        self.challenger = None
        self.player_losing_influence = None
        self.post_influence_loss_state = None
        self.ambassador_cards = []
        self.ambassador_callback = None

    def get_current_player(self):
        return self.players[self.current_player_idx]

    def update(self):
        """Main state machine update loop, called every frame."""
        if self.state == 'INITIAL_REVEAL':
             self.message = f"{self.get_current_player().name}, press 'Reveal Cards' to see your hand."
        elif self.state == 'START_TURN':
            self.action_player = self.get_current_player()
            self.message = f"{self.action_player.name}'s turn. Choose an action."
            if self.action_player.coins >= 10:
                self.state = 'MUST_COUP'
                self.message = f"{self.action_player.name} has 10+ coins. Must Coup."
            else:
                self.state = 'AWAITING_ACTION'

    def handle_click(self, key, mouse_pos):
        """Handles a click on a button or player area."""
        if self.state == 'INITIAL_REVEAL':
            if key == 'Reveal':
                self.cards_revealed_this_turn = True
                self.message = f"{self.get_current_player().name}, memorize your cards."
            elif key == 'Hide':
                self.cards_revealed_this_turn = False
                self.reveal_turns_taken += 1
                if self.reveal_turns_taken >= len(self.players):
                    self.current_player_idx = -1 # so next_turn starts at player 0
                    self.next_turn()
                else:
                    self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        
        elif self.state == 'AWAITING_ACTION' or self.state == 'MUST_COUP':
            self.start_action(key)
        
        elif self.state == 'SELECTING_TARGET':
            if 'player' in key:
                target_id = key['player']
                if target_id != self.action_player.id:
                    self.target_player = self.players[target_id]
                    self.begin_response_phase()
        
        elif self.state == 'AWAITING_RESPONSE':
            player_id, response = key
            if response == 'Pass':
                self.potential_responders.pop(0)
                if not self.potential_responders:
                    self.execute_action()
            elif response == 'Challenge':
                self.challenger = self.players[player_id]
                self.resolve_action_challenge()
            elif response == 'Block':
                self.blocker = self.players[player_id]
                self.begin_block_challenge_phase()

        elif self.state == 'AWAITING_BLOCK_CHALLENGE':
            player_id, response = key
            if response == 'Pass':
                self.message = f"{self.blocker.name} blocks the action. Turn over."
                self.next_turn()
            elif response == 'Challenge':
                self.challenger = self.players[player_id]
                self.resolve_block_challenge()

        elif self.state == 'CHOOSING_INFLUENCE_TO_LOSE':
            card_name = key
            self.player_losing_influence.lose_influence(card_name)
            self.message = f"{self.player_losing_influence.name} lost a {card_name}."
            self.state = self.post_influence_loss_state
            if self.state == 'EXECUTE_ACTION':
                self.execute_action()
            elif self.state == 'NEXT_TURN':
                self.next_turn()

        elif self.state == 'AMBASSADOR_EXCHANGE':
            card_name = key
            self.ambassador_cards.remove(card_name)
            self.action_player.influence.append(card_name)
            if len(self.action_player.influence) == self.ambassador_callback['cards_to_keep']:
                for card in self.ambassador_cards:
                    GameState().add_to_deck(card)
                self.next_turn()

    def start_action(self, action_name):
        self.action = GameState().actions.get(action_name)
        if not self.action: return

        if self.action_player.coins < self.action.coins_needed:
            self.message = "Not enough coins!"
            return

        if self.action.has_target:
            self.state = 'SELECTING_TARGET'
            self.message = f"Select a target for {self.action.name}"
        else:
            self.begin_response_phase()

    def begin_response_phase(self):
        if self.action.name in ['Income']:
            self.execute_action()
            return

        self.potential_responders = [p for p in self.players if p.id != self.action_player.id and not p.is_out]
        if self.target_player and self.target_player in self.potential_responders:
            self.potential_responders.remove(self.target_player)
            self.potential_responders.insert(0, self.target_player)
        
        if self.potential_responders:
            self.state = 'AWAITING_RESPONSE'
            self.message = f"Action: {self.action.name}. Any response?"
        else:
            self.execute_action()

    def execute_action(self):
        try:
            status, msg = self.action.play(self.action_player, self.target_player)
            self.message = f"Action Succeeded: {msg}"
            
            if self.action.name == 'Coup' or self.action.name == 'Assassinate':
                self.player_losing_influence = self.target_player
                self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
                self.post_influence_loss_state = 'NEXT_TURN'
                self.message = f"{self.target_player.name} must lose an influence."
            elif self.action.name == 'Exchange':
                self.handle_ambassador_exchange()
            else:
                self.next_turn()
        except CoupError as e:
            self.message = f"Action failed: {e.message}"
            self.state = 'AWAITING_ACTION'

    def resolve_action_challenge(self):
        action_char = self.action.character
        if self.action_player.has_card(action_char):
            self.message = f"{self.action_player.name} reveals {action_char}! Challenge failed."
            self.action_player.influence.remove(action_char)
            GameState().add_to_deck(action_char)
            self.action_player.influence.append(GameState().draw_card())
            
            self.player_losing_influence = self.challenger
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'EXECUTE_ACTION'
        else:
            self.message = f"{self.action_player.name} was bluffing! They lose an influence."
            self.player_losing_influence = self.action_player
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'NEXT_TURN'

    def begin_block_challenge_phase(self):
        self.state = 'AWAITING_BLOCK_CHALLENGE'
        self.message = f"{self.blocker.name} blocks. {self.action_player.name}, challenge the block?"

    def resolve_block_challenge(self):
        possible_blockers = self.action.blockable_by
        block_successful = any(self.blocker.has_card(card) for card in possible_blockers)

        if block_successful:
            self.message = f"{self.blocker.name} reveals a valid blocker! {self.challenger.name} loses influence."
            self.player_losing_influence = self.challenger
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'NEXT_TURN'
        else:
            self.message = f"{self.blocker.name} was bluffing the block! They lose influence."
            self.player_losing_influence = self.blocker
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'EXECUTE_ACTION'

    def handle_ambassador_exchange(self):
        self.state = 'AMBASSADOR_EXCHANGE'
        cards_to_keep = len(self.action_player.influence)
        self.ambassador_cards = self.action_player.influence[:]
        self.action_player.influence = []
        self.ambassador_cards.append(GameState().draw_card())
        self.ambassador_cards.append(GameState().draw_card())
        self.ambassador_callback = {'cards_to_keep': cards_to_keep}
        self.message = f"{self.action_player.name}, choose {cards_to_keep} card(s) to keep."

    def next_turn(self):
        self.players_who_passed.clear()
        
        # --- SET CONTEXTUAL MESSAGE FOR RESPONDERS ---
        if self.target_player:
            self.message = f"{self.action_player.name} uses {self.action.name} on {self.target_player.name}."
        else:
            self.message = f"{self.action_player.name} uses {self.action.name}."
        # ---------------------------------------------

        if self.action.name == 'Income':
            self.execute_action()
            return
        
        # This logic handles ForeignAid, Tax, Steal, Assassinate, Exchange
        # It correctly identifies who can respond.
        responders = []
        if self.target_player:
             # For targeted actions, only the target and other potential blockers/challengers respond.
             # In Coup, broadcast responses are generally for non-targeted character actions,
             # or actions that everyone can block (like Foreign Aid).
             # For simplicity here, we can broaden the response group.
             responders = [p for p in self.players if p.id != self.action_player.id and not p.is_out]
        else:
             # For broadcast actions like Tax, Foreign Aid, Exchange
             responders = [p for p in self.players if p.id != self.action_player.id and not p.is_out]

        self.potential_responders = responders
        if self.potential_responders:
            # ForeignAid, Tax, Exchange are broadcast. Steal/Assassinate are too, for challenges.
            self.state = 'AWAITING_BROADCAST_RESPONSE'
        else:
            # No one left to respond
            self.execute_action()

# --- GUI Constants ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
RED = (200, 50, 50)
GREEN = (50, 200, 50)
BLUE = (50, 50, 200)
YELLOW = (220, 220, 50)

CARD_WIDTH = 110
CARD_HEIGHT = 165
CARD_MARGIN = 20

PLAYER_AREA_WIDTH = 2 * (CARD_WIDTH + CARD_MARGIN) + 20
PLAYER_AREA_HEIGHT = CARD_HEIGHT + 100

PLAYER_COLORS = [
    (255, 100, 100, 150),
    (100, 255, 100, 150),
    (100, 100, 255, 150),
    (255, 255, 100, 150)
]

class PygameGUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Coup Game")
        self.font = pygame.font.Font(None, 32)
        self.big_font = pygame.font.Font(None, 48)
        self.card_font = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
        self.controller = GameController()
        self.buttons = {}
        self.player_areas = {}

    def run(self):
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked = False
                    # Use the button dictionary from the previous frame for hit detection
                    for key, rect in self.buttons.items():
                        if rect.collidepoint(mouse_pos):
                            self.controller.handle_click(key, mouse_pos)
                            clicked = True
                            break
                    if not clicked and self.controller.state == 'SELECTING_TARGET':
                         for p_id, rect in self.player_areas.items():
                            if rect.collidepoint(mouse_pos):
                                self.controller.handle_click({'player': p_id}, mouse_pos)
                                break
            
            self.controller.update()
            self.draw()
            self.clock.tick(30)
        
        pygame.quit()
        sys.exit()

    def draw(self):
        self.screen.fill(WHITE)
        self.draw_game_message()
        self.draw_players()
        self.draw_ui_elements() # This method will now manage the self.buttons dictionary
        pygame.display.flip()
        
    def draw_button(self, text, rect, key, color, text_color=BLACK):
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, BLACK, rect, 2, border_radius=8)
        text_surf = self.font.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)
        self.buttons[key] = rect

    def draw_players(self):
        positions = [
            (50, 50), (SCREEN_WIDTH - PLAYER_AREA_WIDTH - 50, 50),
            (50, SCREEN_HEIGHT - PLAYER_AREA_HEIGHT - 50), (SCREEN_WIDTH - PLAYER_AREA_WIDTH - 50, SCREEN_HEIGHT - PLAYER_AREA_HEIGHT - 50)
        ]
        self.player_areas.clear()
        
        for i, player in enumerate(self.controller.players):
            x, y = positions[i]
            is_current = (player == self.controller.get_current_player())
            
            if is_current and self.controller.state != 'GAME_OVER':
                pygame.draw.rect(self.screen, YELLOW, (x-5, y-5, PLAYER_AREA_WIDTH+10, PLAYER_AREA_HEIGHT+10), border_radius=12)

            area_rect = pygame.Rect(x,y, PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT)
            self.player_areas[i] = area_rect
            
            surface = pygame.Surface((PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT), pygame.SRCALPHA)
            surface.fill(PLAYER_COLORS[i])
            self.screen.blit(surface, (x, y))
            pygame.draw.rect(self.screen, BLACK, area_rect, 3, border_radius=8)
            
            name_text = self.big_font.render(player.name, True, BLACK)
            self.screen.blit(name_text, (x + 15, y + 10))
            coins_text = self.font.render(f"Coins: {player.coins}", True, BLACK)
            self.screen.blit(coins_text, (x + 15, y + 55))

            if player.is_out:
                out_text = self.big_font.render("ELIMINATED", True, RED)
                out_rect = out_text.get_rect(center=area_rect.center)
                self.screen.blit(out_text, out_rect)
                continue

            for j, card_name in enumerate(player.influence):
                card_x = x + 15 + j * (CARD_WIDTH + CARD_MARGIN)
                card_y = y + 95
                card_rect = pygame.Rect(card_x, card_y, CARD_WIDTH, CARD_HEIGHT)
                pygame.draw.rect(self.screen, BLUE, card_rect, border_radius=8)
                
                # Determine if cards should be shown
                show_cards = False
                if is_current:
                    if self.controller.state == 'INITIAL_REVEAL' and self.controller.cards_revealed_this_turn:
                        show_cards = True
                    elif self.controller.state not in ['INITIAL_REVEAL', 'GAME_OVER']:
                        show_cards = True

                if show_cards:
                    card_text = self.card_font.render(card_name, True, WHITE)
                    text_r = card_text.get_rect(center=card_rect.center)
                    self.screen.blit(card_text, text_r)
                else:
                    q_mark = self.big_font.render("?", True, WHITE)
                    q_r = q_mark.get_rect(center=card_rect.center)
                    self.screen.blit(q_mark, q_r)

    def draw_game_message(self):
        msg_surf = self.big_font.render(self.controller.message, True, BLACK)
        msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, 40))
        self.screen.blit(msg_surf, msg_rect)

    def draw_ui_elements(self):
        self.buttons.clear() # Clear buttons at the start of drawing UI
        state = self.controller.state
        
        if state == 'INITIAL_REVEAL':
            if not self.controller.cards_revealed_this_turn:
                rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2, 300, 50)
                self.draw_button("Reveal Cards", rect, 'Reveal', GREEN)
            else:
                rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2, 300, 50)
                self.draw_button("Hide & Pass Turn", rect, 'Hide', RED)

        elif state == 'AWAITING_ACTION' or state == 'MUST_COUP':
            actions = list(GameState().actions.keys())
            if self.controller.state == 'MUST_COUP': actions = ['Coup']
            
            for i, name in enumerate(actions):
                rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 - 150 + i * 45, 300, 40)
                self.draw_button(name, rect, name, GREEN)

        elif state == 'AWAITING_RESPONSE':
            if not self.controller.potential_responders: return
            player = self.controller.potential_responders[0]
            action = self.controller.action
            self.draw_button(f"{player.name}: Pass", pygame.Rect(SCREEN_WIDTH/2 - 320, SCREEN_HEIGHT/2, 200, 50), (player.id, 'Pass'), GRAY)
            if action.character:
                 self.draw_button(f"{player.name}: Challenge", pygame.Rect(SCREEN_WIDTH/2 - 100, SCREEN_HEIGHT/2, 200, 50), (player.id, 'Challenge'), YELLOW)
            if action.blockable_by:
                 self.draw_button(f"{player.name}: Block", pygame.Rect(SCREEN_WIDTH/2 + 120, SCREEN_HEIGHT/2, 200, 50), (player.id, 'Block'), RED)

        elif state == 'AWAITING_BLOCK_CHALLENGE':
             player = self.controller.action_player
             self.draw_button(f"{player.name}: Pass", pygame.Rect(SCREEN_WIDTH/2 - 270, SCREEN_HEIGHT/2, 260, 50), (player.id, 'Pass'), GRAY)
             self.draw_button(f"{player.name}: Challenge Block", pygame.Rect(SCREEN_WIDTH/2 + 10, SCREEN_HEIGHT/2, 260, 50), (player.id, 'Challenge'), YELLOW)

        elif state == 'CHOOSING_INFLUENCE_TO_LOSE':
            player = self.controller.player_losing_influence
            for i, card in enumerate(player.influence):
                rect = pygame.Rect(SCREEN_WIDTH/2 - 155 + i * 220, SCREEN_HEIGHT/2, 200, 60)
                self.draw_button(f"Lose {card}", rect, card, RED)
        
        elif state == 'AMBASSADOR_EXCHANGE':
            for i, card in enumerate(self.controller.ambassador_cards):
                rect = pygame.Rect(100 + i * 220, SCREEN_HEIGHT/2, 200, 60)
                self.draw_button(f"Keep {card}", rect, card, GREEN)

if __name__ == '__main__':
    game_gui = PygameGUI()
    game_gui.run()
