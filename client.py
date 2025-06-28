import pygame
import sys
import requests
import json
import time
import random
from collections import Counter

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
COLOR_INACTIVE = pygame.Color('lightskyblue3')
COLOR_ACTIVE = pygame.Color('dodgerblue2')


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

SERVER_URL = "http://127.0.0.1:8000" # Use 127.0.0.1 for local testing

class PygameGUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.font = pygame.font.Font(None, 32)
        self.big_font = pygame.font.Font(None, 48)
        self.title_font = pygame.font.Font(None, 96)
        self.card_font = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
        
        self.FETCH_STATE_EVENT = pygame.USEREVENT + 1

        # Initialize client state
        self.reset_to_menu()
        
        pygame.display.set_caption(f"Coup - Not Connected")

    def reset_to_menu(self):
        """Resets the client to the main menu state, clearing all game data."""
        self.player_id = None
        self.game_id = None
        self.player_name = "" # Start with an empty name
        self.ui_state = 'MENU' # MENU, WAITING_IN_LOBBY, PLAYING, GAME_OVER, FAILED
        self.game_state = {} 
        self.buttons = {}
        self.player_areas = {}
        self.exchange_selection = []
        
        # Add input box for player name
        self.input_box = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 - 20, 300, 50)
        self.input_active = True

        pygame.time.set_timer(self.FETCH_STATE_EVENT, 0) # Stop polling

    def matchmake(self):
        """Attempts to join a game lobby via the server's matchmaking."""
        # Use the entered player name, or a default if empty (though UI prevents this)
        player_name_to_send = self.player_name.strip() if self.player_name.strip() != "" else "Player" + str(random.randint(100,999))

        print(f"Finding a match as {player_name_to_send}...")
        self.ui_state = 'WAITING_IN_LOBBY'
        self.game_state['message'] = "Finding a match..."
        try:
            payload = {'name': player_name_to_send}
            headers = {'Content-Type': 'application/json'}
            response = requests.post(f"{SERVER_URL}/matchmake", data=json.dumps(payload), headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                self.player_id = data['player_id']
                self.game_id = data['game_id'] 
                
                pygame.display.set_caption(f"Coup - {self.player_name} (Game {self.game_id})")
                
                pygame.time.set_timer(self.FETCH_STATE_EVENT, 500) 
                self.fetch_game_state()
            else:
                self.game_state['message'] = response.json().get('error', 'Failed to find a match')
                self.ui_state = 'FAILED'

        except requests.exceptions.RequestException as e:
            print(f"Error finding match: {e}")
            self.game_state['message'] = "Could not connect to server."
            self.ui_state = 'FAILED'

    def fetch_game_state(self):
        """Gets the latest game state from the server for our specific game instance."""
        if self.player_id is None or self.game_id is None: return
        try:
            response = requests.get(f"{SERVER_URL}/state?player_id={self.player_id}&game_id={self.game_id}")
            response.raise_for_status()
            
            new_game_state = response.json()

            if self.ui_state == 'WAITING_IN_LOBBY' and new_game_state.get('game_state') != 'WAITING_FOR_PLAYERS':
                self.ui_state = 'PLAYING'

            if new_game_state.get('game_state') == 'GAME_OVER':
                self.ui_state = 'GAME_OVER'

            self.game_state = new_game_state
            
            if self.game_state.get('game_state') != 'AMBASSADOR_EXCHANGE':
                self.exchange_selection = []

        except requests.exceptions.RequestException as e:
            print(f"Error fetching state: {e}")
            self.game_state['message'] = "Error connecting to server..."

    def post_action(self, payload):
        """Sends a player action to the correct game instance on the server."""
        if self.player_id is None or self.game_id is None: return
        try:
            headers = {'Content-Type': 'application/json'}
            payload['player_id'] = self.player_id
            payload['game_id'] = self.game_id
            
            response = requests.post(f"{SERVER_URL}/action", data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            self.fetch_game_state()
        except requests.exceptions.RequestException as e:
            print(f"Error posting action: {e}")
            self.game_state['message'] = "Error sending action to server..."

    def send_quit_signal(self):
        """Informs the server that this client is quitting its specific game instance."""
        if self.player_id is None or self.game_id is None: return
        try:
            payload = {'player_id': self.player_id, 'game_id': self.game_id}
            headers = {'Content-Type': 'application/json'}
            requests.post(f"{SERVER_URL}/quit", data=json.dumps(payload), headers=headers, timeout=1)
        except requests.exceptions.RequestException as e:
            print(f"Could not send quit signal to server: {e}")

    def run(self):
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.send_quit_signal()
                    running = False
                
                # --- Event handling for name input box ---
                if self.ui_state == 'MENU':
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.input_active = self.input_box.collidepoint(event.pos)
                    if event.type == pygame.KEYDOWN and self.input_active:
                        if event.key == pygame.K_RETURN:
                            if self.player_name.strip() != "":
                                self.matchmake()
                        elif event.key == pygame.K_BACKSPACE:
                            self.player_name = self.player_name[:-1]
                        else:
                            self.player_name += event.unicode
                
                if self.ui_state in ['PLAYING', 'WAITING_IN_LOBBY', 'GAME_OVER']:
                    if event.type == self.FETCH_STATE_EVENT:
                        self.fetch_game_state()
                
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(mouse_pos)
            
            self.draw()
            self.clock.tick(30)
        
        pygame.quit()
        sys.exit()

    def handle_click(self, mouse_pos):
        # Always check for button clicks first
        for key, rect in self.buttons.items():
            if rect.collidepoint(mouse_pos):
                key_type, value = key

                if self.ui_state == 'MENU' and key_type == 'action' and value == 'Match':
                    if self.player_name.strip() != "":
                        self.matchmake()
                    return
                
                if self.ui_state == 'GAME_OVER' and key_type == 'action' and value == 'BackToMenu':
                    self.reset_to_menu()
                    return

                if self.ui_state == 'PLAYING':
                    if key_type == 'select_exchange':
                        num_to_keep = self.game_state.get('ui_context', {}).get('num_to_keep', 0)
                        toggled_index, card_name = value[1], value[0]
                        is_selected = any(item[1] == toggled_index for item in self.exchange_selection)
                        if is_selected:
                            self.exchange_selection = [item for item in self.exchange_selection if item[1] != toggled_index]
                        elif len(self.exchange_selection) < num_to_keep:
                            self.exchange_selection.append((card_name, toggled_index))
                        return 
                    
                    if key_type == 'action' and value == 'ConfirmExchange':
                        payload = {'action': 'ConfirmExchange', 'cards': [card for card, index in self.exchange_selection]}
                    else:
                        payload = {key_type: value}
                    
                    self.post_action(payload)
                    return

        # Check for target selection clicks (only in PLAYING state)
        if self.ui_state == 'PLAYING':
            gs = self.game_state
            if gs.get('game_state') == 'SELECTING_TARGET' and gs.get('your_id') == gs.get('current_player_idx'):
                for p_id, rect in self.player_areas.items():
                    if p_id != self.player_id and rect.collidepoint(mouse_pos):
                        action_name = gs.get('ui_context', {}).get('action')
                        if action_name:
                            self.post_action({'action': action_name, 'target_id': p_id})
                        else:
                            print("Error: Client in SELECTING_TARGET state but server did not provide an action name.")
                        return

    def draw(self):
        self.screen.fill(WHITE)
        self.buttons.clear()

        if self.ui_state == 'MENU':
            self.draw_menu_screen()
        elif self.ui_state == 'FAILED':
            msg_surf = self.big_font.render(self.game_state.get('message', "Failed to connect"), True, RED)
            msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2))
            self.screen.blit(msg_surf, msg_rect)
        elif self.ui_state == 'WAITING_IN_LOBBY':
            self.draw_lobby_screen()
        elif self.ui_state == 'GAME_OVER':
            self.draw_game_over_screen()
        elif self.ui_state == 'PLAYING':
            if not self.game_state:
                msg_surf = self.big_font.render("Connecting to server...", True, BLACK)
                msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2))
                self.screen.blit(msg_surf, msg_rect)
            else:
                self.draw_game_message()
                self.draw_players()
                self.draw_ui_elements()
        
        pygame.display.flip()
        
    def draw_menu_screen(self):
        # Draw Title
        title_surf = self.title_font.render("COUP", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2 - 150))
        self.screen.blit(title_surf, title_rect)

        # Draw Name Input Box
        label_surf = self.big_font.render("Enter Your Name:", True, BLACK)
        label_rect = label_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2 - 70))
        self.screen.blit(label_surf, label_rect)

        color = COLOR_ACTIVE if self.input_active else COLOR_INACTIVE
        pygame.draw.rect(self.screen, color, self.input_box, 2, border_radius=5)
        txt_surface = self.big_font.render(self.player_name, True, BLACK)
        self.screen.blit(txt_surface, (self.input_box.x+10, self.input_box.y+5))
        self.input_box.w = max(300, txt_surface.get_width()+20) # Resize box dynamically

        # Draw Match Button
        button_rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 + 70, 300, 80)
        button_color = GREEN if self.player_name.strip() != "" else GRAY
        self.draw_button("Find Match", button_rect, ('action', 'Match'), button_color)

    def draw_lobby_screen(self):
        msg = self.game_state.get('message', "Waiting for players...")
        msg_surf = self.big_font.render(msg, True, BLACK)
        msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2))
        self.screen.blit(msg_surf, msg_rect)
        self.draw_players()

    def draw_game_over_screen(self):
        msg = self.game_state.get('message', "Game Over!")
        msg_surf = self.title_font.render(msg, True, BLACK)
        msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, SCREEN_HEIGHT/2 - 100))
        self.screen.blit(msg_surf, msg_rect)

        button_rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 + 50, 300, 80)
        self.draw_button("Back to Menu", button_rect, ('action', 'BackToMenu'), BLUE)

    def draw_button(self, text, rect, key, color, border_color=BLACK):
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=8)
        text_surf = self.font.render(text, True, BLACK)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)
        self.buttons[key] = rect

    def draw_players(self):
        positions = [
            (50, 50), (SCREEN_WIDTH - PLAYER_AREA_WIDTH - 50, 50),
            (50, SCREEN_HEIGHT - PLAYER_AREA_HEIGHT - 50), (SCREEN_WIDTH - PLAYER_AREA_WIDTH - 50, SCREEN_HEIGHT - PLAYER_AREA_HEIGHT - 50)
        ]
        self.player_areas.clear()
        
        for player_data in self.game_state.get('players', []):
            i = player_data['id']
            x, y = positions[i]

            is_me = (i == self.player_id)
            is_current = (i == self.game_state.get('current_player_idx'))
            
            if is_current and self.game_state.get('game_state') not in ['GAME_OVER', 'WAITING_FOR_PLAYERS']:
                pygame.draw.rect(self.screen, YELLOW, (x-5, y-5, PLAYER_AREA_WIDTH+10, PLAYER_AREA_HEIGHT+10), border_radius=12)

            area_rect = pygame.Rect(x, y, PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT)
            self.player_areas[i] = area_rect
            
            surface = pygame.Surface((PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT), pygame.SRCALPHA)
            surface.fill(PLAYER_COLORS[i])
            self.screen.blit(surface, (x, y))
            pygame.draw.rect(self.screen, BLACK, area_rect, 3, border_radius=8)
            
            name_text = self.big_font.render(player_data['name'], True, BLACK)
            self.screen.blit(name_text, (x + 15, y + 10))
            coins_text = self.font.render(f"Coins: {player_data['coins']}", True, BLACK)
            self.screen.blit(coins_text, (x + 15, y + 55))

            if player_data['is_out']:
                out_text = self.big_font.render("ELIMINATED", True, RED)
                out_rect = out_text.get_rect(center=area_rect.center)
                self.screen.blit(out_text, out_rect)
                continue

            my_cards = self.game_state.get('your_cards', [])
            for j in range(player_data['influence_count']):
                card_x = x + 15 + j * (CARD_WIDTH + CARD_MARGIN)
                card_y = y + 95
                card_rect = pygame.Rect(card_x, card_y, CARD_WIDTH, CARD_HEIGHT)
                pygame.draw.rect(self.screen, BLUE, card_rect, border_radius=8)
                
                if is_me and j < len(my_cards):
                    card_text = self.card_font.render(my_cards[j], True, WHITE)
                    text_r = card_text.get_rect(center=card_rect.center)
                    self.screen.blit(card_text, text_r)
                else:
                    q_mark = self.big_font.render("?", True, WHITE)
                    q_r = q_mark.get_rect(center=card_rect.center)
                    self.screen.blit(q_mark, q_r)

    def draw_game_message(self):
        msg = self.game_state.get('message', 'Loading...')
        msg_surf = self.big_font.render(msg, True, BLACK)
        msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH/2, 40))
        self.screen.blit(msg_surf, msg_rect)

    def draw_ui_elements(self):
        gs = self.game_state
        ui_context = gs.get('ui_context', {})
        is_my_turn = gs.get('your_id') == gs.get('current_player_idx')
        
        # --- Action Buttons ---
        if is_my_turn and gs.get('game_state') in ['AWAITING_ACTION', 'MUST_COUP']:
            actions = ['Income', 'ForeignAid', 'Tax', 'Steal', 'Assassinate', 'Exchange', 'Coup']
            if gs.get('game_state') == 'MUST_COUP': actions = ['Coup']
            
            for i, name in enumerate(actions):
                rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 - 150 + i * 45, 300, 40)
                self.draw_button(name, rect, ('action', name), GREEN)

        # --- Response Buttons (FIXED) ---
        # The server will only send this context to players who should respond.
        if ui_context.get('type') == 'broadcast_response':
            can_challenge = ui_context.get('can_challenge', False)
            can_block = ui_context.get('can_block', False)
            
            buttons_to_draw = [{'text': 'Pass', 'key': ('response', 'Pass'), 'color': GRAY}]
            if can_challenge: buttons_to_draw.append({'text': 'Challenge', 'key': ('response', 'Challenge'), 'color': YELLOW})
            if can_block: buttons_to_draw.append({'text': 'Block', 'key': ('response', 'Block'), 'color': RED})
            
            total_width = len(buttons_to_draw) * 210 - 10
            start_x = SCREEN_WIDTH/2 - total_width/2
            
            for i, btn_data in enumerate(buttons_to_draw):
                rect = pygame.Rect(start_x + i * 210, SCREEN_HEIGHT/2, 200, 50)
                self.draw_button(btn_data['text'], rect, btn_data['key'], btn_data['color'])

        # --- Block Challenge Buttons ---
        if ui_context.get('type') == 'challenge_block' and is_my_turn:
             self.draw_button("Pass", pygame.Rect(SCREEN_WIDTH/2 - 270, SCREEN_HEIGHT/2, 260, 50), ('response', 'Pass'), GRAY)
             self.draw_button("Challenge Block", pygame.Rect(SCREEN_WIDTH/2 + 10, SCREEN_HEIGHT/2, 260, 50), ('response', 'Challenge'), YELLOW)

        # --- Lose Influence Buttons (FIXED) ---
        # Check the ID from the ui_context, not the root game state.
        if ui_context.get('type') == 'lose_influence' and ui_context.get('player_losing_influence_id') == gs.get('your_id'):
            cards = ui_context.get('cards', [])
            num_cards = len(cards)
            for i, card in enumerate(cards):
                rect = pygame.Rect(SCREEN_WIDTH/2 - (num_cards * 220)/2 + 10 + i * 220, SCREEN_HEIGHT/2, 200, 60)
                self.draw_button(f"Lose {card}", rect, ('card', card), RED)
        
        # --- Ambassador Exchange Buttons ---
        if ui_context.get('type') == 'ambassador_exchange' and is_my_turn:
            cards = ui_context.get('cards', [])
            num_to_keep = ui_context.get('num_to_keep', 0)

            total_width = len(cards) * 150 - 10
            start_x = SCREEN_WIDTH/2 - total_width/2
            for i, card in enumerate(cards):
                rect = pygame.Rect(start_x + i * 150, SCREEN_HEIGHT/2 - 50, 140, 50)
                is_selected = any(item[1] == i for item in self.exchange_selection)
                border_color = GREEN if is_selected else BLACK
                key = ('select_exchange', (card, i))
                self.draw_button(card, rect, key, GRAY, border_color)
            
            if len(self.exchange_selection) == num_to_keep:
                confirm_rect = pygame.Rect(SCREEN_WIDTH/2 - 150, SCREEN_HEIGHT/2 + 50, 300, 50)
                self.draw_button(f"Confirm Exchange", confirm_rect, ('action', 'ConfirmExchange'), GREEN)


if __name__ == '__main__':
    gui = PygameGUI()
    gui.run()
