import sys
import os.path
import uuid
from glob import glob
from datetime import datetime
import json
from urllib.parse import urlparse, parse_qs
from collections import Counter
import random
import threading

# =================================================================================
# Core Game Logic
# =================================================================================

class Action:
    name = ""
    blockable_by = []
    has_target = False
    coins_needed = 0
    character = None
    can_be_bluffed = False
    def play(self, player, target=None): return True, "Success"

class Income(Action):
    name = "Income"
    def play(self, player, target=None): player.coins += 1; return True, "Success"

class ForeignAid(Action):
    name = "ForeignAid"
    blockable_by = ['Duke']
    can_be_bluffed = False
    def play(self, player, target=None): player.coins += 2; return True, "Success"

class Coup(Action):
    name = "Coup"
    has_target = True
    coins_needed = 7
    def play(self, player, target=None): return True, "Success"

class Tax(Action):
    name = "Tax"
    character = 'Duke'
    can_be_bluffed = True
    def play(self, player, target=None): player.coins += 3; return True, "Success"

class Steal(Action):
    name = "Steal"
    character = 'Captain'
    blockable_by = ['Captain', 'Ambassador']
    has_target = True
    can_be_bluffed = True
    def play(self, player, target=None): 
        stolen = min(2, target.coins)
        target.coins -= stolen
        player.coins += stolen
        return True, f"Stole {stolen} coins"

class Assassinate(Action):
    name = "Assassinate"
    character = 'Assassin'
    blockable_by = ['Contessa']
    has_target = True
    coins_needed = 3
    can_be_bluffed = True
    def play(self, player, target=None): return True, "Success"

class Exchange(Action):
    name = "Exchange"
    character = 'Ambassador'
    can_be_bluffed = True
    def play(self, player, target=None): return True, "Success"

class GameState:
    _instance = None
    def __new__(cls):
        if not cls._instance: cls._instance = super(GameState, cls).__new__(cls)
        return cls._instance
    
    def initialize(self):
        self.actions = {'Income': Income(), 'ForeignAid': ForeignAid(), 'Coup': Coup(), 'Tax': Tax(), 'Steal': Steal(), 'Assassinate': Assassinate(), 'Exchange': Exchange()}
        self.cards_available = ['Duke', 'Captain', 'Assassin', 'Ambassador', 'Contessa']

    def get_new_deck(self):
        deck = self.cards_available * 3
        random.shuffle(deck)
        return deck

class Player:
    def __init__(self, player_id, name, deck):
        self.id = player_id
        self.name = name
        self.coins = 2
        self.influence = [deck.pop(), deck.pop()]
        self.is_out = False
    def lose_influence(self, card_name):
        if card_name in self.influence: self.influence.remove(card_name)
        if not self.influence: self.is_out = True
    def has_card(self, card_name): return card_name in self.influence
    def to_dict_for_others(self): return {'id': self.id, 'name': self.name, 'coins': self.coins, 'influence_count': len(self.influence), 'is_out': self.is_out}

class GameController:
    """Manages ONE game instance/room."""
    def __init__(self, num_players=4):
        self.num_players_required = num_players
        self.deck = GameState().get_new_deck()
        self.players = []
        self.state = 'WAITING_FOR_PLAYERS'
        self.current_player_idx = 0
        self.message = f"Waiting for players..."
        self.action = None; self.action_player = None; self.target_player = None; self.potential_responders = []; self.blocker = None; self.challenger = None; self.player_losing_influence = None; self.post_influence_loss_state = None; self.ambassador_cards = []; self.pre_exchange_influence_count = 0
        self.players_who_passed = set()

    def add_player(self, name):
        if len(self.players) >= self.num_players_required:
            return None 
        player_id = len(self.players)
        new_player = Player(player_id, name, self.deck)
        self.players.append(new_player)
        self.message = f"Waiting for {self.num_players_required - len(self.players)} more players..."
        if len(self.players) == self.num_players_required:
            self.state = 'AWAITING_ACTION'
            self.message = f"Game starting! {self.players[0].name}'s turn."
        return player_id

    def eliminate_player(self, player_id):
        if 0 <= player_id < len(self.players):
            player = self.players[player_id]
            if not player.is_out:
                player.is_out = True
                player.coins = 0 # Set coins to zero
                for card in player.influence:
                    self.deck.append(card)
                random.shuffle(self.deck)
                player.influence = []
                self.message = f"{player.name} has been eliminated."
                
                # Check if the eliminated player was the last one needed to respond
                if self.state in ['AWAITING_BROADCAST_RESPONSE']:
                    self.check_all_passed()
                # If the current player is eliminated, advance the turn
                elif self.current_player_idx == player_id:
                    self.next_turn()

    def get_state_for_player(self, player_id):
        if player_id >= len(self.players): return {'error': 'Player not joined yet'}
        player = self.players[player_id]
        state = {'game_state': self.state, 'message': self.message, 'your_id': player.id, 'your_cards': player.influence, 'players': [p.to_dict_for_others() for p in self.players], 'current_player_idx': self.current_player_idx, 'ui_context': {}}
        
        if self.state == 'SELECTING_TARGET' and self.action_player.id == player_id:
            state['ui_context'] = {'type': 'selecting_target', 'action': self.action.name}
        elif self.state == 'AWAITING_BROADCAST_RESPONSE':
            if any(p.id == player_id for p in self.potential_responders):
                action_name = self.action.name
                can_challenge = self.action.can_be_bluffed
                can_block = (action_name == 'ForeignAid')
                if action_name in ['Steal', 'Assassinate']:
                    can_block = True 
                state['ui_context'] = {
                    'type': 'broadcast_response', 'action': action_name,
                    'can_challenge': can_challenge, 'can_block': can_block
                }
        elif self.state == 'AWAITING_BLOCK_CHALLENGE' and self.action_player.id == player_id:
            state['ui_context'] = {'type': 'challenge_block'}
        elif self.state == 'CHOOSING_INFLUENCE_TO_LOSE' and self.player_losing_influence and self.player_losing_influence.id == player_id:
            state['ui_context'] = {'type': 'lose_influence', 'cards': self.player_losing_influence.influence, 'player_losing_influence_id': self.player_losing_influence.id}
        elif self.state == 'AMBASSADOR_EXCHANGE' and self.action_player.id == player_id:
            state['ui_context'] = {'type': 'ambassador_exchange', 'cards': self.ambassador_cards, 'num_to_keep': self.pre_exchange_influence_count}
        
        return state

    def handle_action(self, data):
        player_id = data.get('player_id')
        if self.state in ['AWAITING_ACTION', 'MUST_COUP']:
            if player_id != self.current_player_idx: return
            self.start_action(data.get('action'))
        elif self.state == 'SELECTING_TARGET':
            if player_id != self.action_player.id: return
            target_id = data.get('target_id')
            if target_id is not None:
                # --- FIX: Check if target is already eliminated ---
                target_player = self.players[target_id]
                if target_player.is_out:
                    self.message = f"{target_player.name} is already eliminated. Choose another target."
                    return # Stay in SELECTING_TARGET state with the new message
                
                self.target_player = target_player
                self.begin_response_phase()
        elif self.state == 'AWAITING_BROADCAST_RESPONSE':
            if not any(p.id == player_id for p in self.potential_responders): return
            response = data.get('response')
            if response in ['Challenge', 'Block']:
                if response == 'Challenge': 
                    self.challenger = self.players[player_id]
                    self.resolve_action_challenge()
                elif response == 'Block': 
                    self.blocker = self.players[player_id]
                    self.state = 'AWAITING_BLOCK_CHALLENGE'
                    self.message = f"{self.blocker.name} blocks. {self.action_player.name}, do you challenge?"
                self.potential_responders = []
                self.players_who_passed.clear()
            elif response == 'Pass':
                self.players_who_passed.add(player_id)
                self.check_all_passed()
        elif self.state == 'AWAITING_BLOCK_CHALLENGE':
            if player_id != self.action_player.id: return
            if data.get('response') == 'Pass':
                self.message = f"Block by {self.blocker.name} succeeds."
                self.next_turn()
            elif data.get('response') == 'Challenge':
                self.challenger = self.action_player
                self.resolve_block_challenge()
        elif self.state == 'CHOOSING_INFLUENCE_TO_LOSE':
            if not self.player_losing_influence or player_id != self.player_losing_influence.id: return
            card_to_lose = data.get('card')
            # Ensure the player actually loses an influence, even if card name is wrong
            if card_to_lose not in self.player_losing_influence.influence and self.player_losing_influence.influence:
                card_to_lose = self.player_losing_influence.influence[0]
            
            self.player_losing_influence.lose_influence(card_to_lose)
            
            if self.player_losing_influence.is_out:
                self.eliminate_player(self.player_losing_influence.id)
            
            if self.post_influence_loss_state == 'EXECUTE_ACTION': self.execute_action()
            else: self.next_turn()
        elif self.state == 'AMBASSADOR_EXCHANGE':
            if player_id != self.action_player.id: return
            self.handle_ambassador_cards(data.get('cards', []))

    def start_action(self, action_name):
        self.action = GameState().actions.get(action_name)
        if not self.action: return
        self.action_player = self.players[self.current_player_idx]
        
        if self.action_player.coins < self.action.coins_needed:
            self.message = f"Not enough coins for {action_name}"
            return

        if self.action.coins_needed > 0:
            self.action_player.coins -= self.action.coins_needed
        
        if self.action.has_target:
            self.state = 'SELECTING_TARGET'
            self.message = f"Select target for {self.action.name}"
        else:
            self.begin_response_phase()

    def begin_response_phase(self):
        self.players_who_passed.clear()
        action_name = self.action.name
        if self.target_player: self.message = f"{self.action_player.name} uses {action_name} on {self.target_player.name}."
        else: self.message = f"{self.action_player.name} uses {action_name}."
        if action_name == 'Income':
            self.execute_action()
            return
        if action_name in ['Steal', 'Assassinate', 'Coup']:
            if self.target_player and not self.target_player.is_out: self.potential_responders = [self.target_player]
            else: self.potential_responders = []
        else:
            self.potential_responders = [p for p in self.players if p.id != self.action_player.id and not p.is_out]
        if self.potential_responders: self.state = 'AWAITING_BROADCAST_RESPONSE'
        else: self.execute_action()

    def check_all_passed(self):
        responder_ids = {p.id for p in self.potential_responders if not p.is_out}
        if self.players_who_passed.issuperset(responder_ids):
            self.execute_action()

    def execute_action(self):
        self.message = f"{self.action_player.name}'s {self.action.name} succeeds."
        self.action.play(self.action_player, self.target_player)
        if self.action.name in ['Coup', 'Assassinate']:
            self.player_losing_influence = self.target_player
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'NEXT_TURN'
            self.message = f"{self.target_player.name} must lose an influence."
        elif self.action.name == 'Exchange':
            self.state = 'AMBASSADOR_EXCHANGE'
            self.pre_exchange_influence_count = len(self.action_player.influence)
            self.ambassador_cards = self.action_player.influence[:] + [self.deck.pop() for _ in range(2) if self.deck]
            self.action_player.influence = []
        else:
            self.next_turn()

    def resolve_action_challenge(self):
        char = self.action.character
        if self.action_player.has_card(char):
            self.message = f"{self.action_player.name} reveals {char}!"
            self.action_player.influence.remove(char)
            self.deck.append(char)
            random.shuffle(self.deck)
            self.action_player.influence.append(self.deck.pop())
            self.player_losing_influence = self.challenger
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'EXECUTE_ACTION'
        else:
            self.message = f"{self.action_player.name} was bluffing!"
            self.player_losing_influence = self.action_player
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'NEXT_TURN'

    def resolve_block_challenge(self):
        possible = self.action.blockable_by
        if any(self.blocker.has_card(card) for card in possible):
            self.message = f"Block by {self.blocker.name} was valid!"
            self.player_losing_influence = self.challenger
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'NEXT_TURN'
        else:
            self.message = f"Block by {self.blocker.name} was a bluff!"
            self.player_losing_influence = self.blocker
            self.state = 'CHOOSING_INFLUENCE_TO_LOSE'
            self.post_influence_loss_state = 'EXECUTE_ACTION'

    def handle_ambassador_cards(self, cards_to_keep):
        if len(cards_to_keep) != self.pre_exchange_influence_count:
            self.message = f"Invalid selection. Must choose {self.pre_exchange_influence_count}."
            return
        offered_counts = Counter(self.ambassador_cards)
        kept_counts = Counter(cards_to_keep)
        if any(kept_counts[card] > offered_counts[card] for card in kept_counts):
            self.message = "Invalid selection. Card not in offer."
            return
        cards_to_return = self.ambassador_cards[:]
        for card in cards_to_keep: cards_to_return.remove(card)
        self.action_player.influence = cards_to_keep
        self.deck.extend(cards_to_return)
        random.shuffle(self.deck)
        self.next_turn()

    def next_turn(self):
        self.action = None; self.action_player = None; self.target_player = None; self.potential_responders = []; self.blocker = None; self.challenger = None; self.player_losing_influence = None; self.post_influence_loss_state = None; self.players_who_passed.clear()
        alive = [p for p in self.players if not p.is_out]
        if len(alive) <= 1:
            self.state = 'GAME_OVER'
            self.message = f"Winner: {alive[0].name if alive else 'None'}"
            return
        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        while self.players[self.current_player_idx].is_out:
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        self.state = 'AWAITING_ACTION'
        if self.players[self.current_player_idx].coins >= 10:
            self.state = 'MUST_COUP'
            self.message = f"{self.players[self.current_player_idx].name} must Coup."
        else:
            self.message = f"{self.players[self.current_player_idx].name}'s turn."


class ServerManager:
    """Manages all game instances."""
    def __init__(self):
        self.game_instances = {}
        self.next_game_id = 0
        self.lock = threading.Lock() 

    def find_or_create_game(self, player_name):
        with self.lock:
            for game_id, instance in self.game_instances.items():
                if instance.state == 'WAITING_FOR_PLAYERS' and len(instance.players) < instance.num_players_required:
                    player_id = instance.add_player(player_name)
                    return game_id, player_id
            new_game_id = self.next_game_id
            new_game_instance = GameController()
            self.game_instances[new_game_id] = new_game_instance
            self.next_game_id += 1
            player_id = new_game_instance.add_player(player_name)
            return new_game_id, player_id

    def get_game(self, game_id):
        return self.game_instances.get(game_id)


# =================================================================================
# HTTP Server Foundation (from http.py)
# =================================================================================
class HttpServer:
    def __init__(self):
        # Global instances for the server are now tied to the HttpServer instance
        GameState().initialize()
        self.server_manager = ServerManager()
        self.sessions={}
        self.types={}
        self.types['.pdf']='application/pdf'
        self.types['.jpg']='image/jpeg'
        self.types['.txt']='text/plain'
        self.types['.html']='text/html'
        self.types['.json']='application/json' # Added for API responses

    def response(self, kode=404, message='Not Found', messagebody=bytes(), headers={}):
        tanggal = datetime.now().strftime('%c')
        resp=[]
        resp.append(f"HTTP/1.0 {kode} {message}\r\n")
        resp.append(f"Date: {tanggal}\r\n")
        resp.append("Connection: close\r\n")
        resp.append("Server: CoupServer/1.0\r\n")
        resp.append(f"Content-Length: {len(messagebody)}\r\n")
        resp.append("Access-Control-Allow-Origin: *\r\n") # Added for CORS
        for kk in headers:
            resp.append(f"{kk}:{headers[kk]}\r\n")
        resp.append("\r\n")

        response_headers = "".join(resp)
        if not isinstance(messagebody, bytes):
            messagebody = messagebody.encode()

        return response_headers.encode() + messagebody

    def proses(self, data):
        requests = data.split("\r\n")
        baris = requests[0]
        
        header_end_index = data.find('\r\n\r\n')
        body = ""
        if header_end_index != -1:
            body = data[header_end_index+4:]

        j = baris.split(" ")
        try:
            method = j[0].upper().strip()
            object_address = j[1].strip()

            if (method=='GET'):
                return self.http_get(object_address)
            if (method=='POST'):
                return self.http_post(object_address, body)
            if (method=='OPTIONS'):
                return self.response(200, 'OK', '', {'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'})
            else:
                return self.response(400,'Bad Request','',{})
        except IndexError:
            return self.response(400,'Bad Request','',{})

    def http_get(self, object_address):
        if object_address.startswith('/state'):
            try:
                params = parse_qs(urlparse(object_address).query)
                player_id = int(params.get('player_id', [0])[0])
                game_id = int(params.get('game_id', [0])[0])
                
                game = self.server_manager.get_game(game_id)
                if game:
                    response_data = game.get_state_for_player(player_id)
                    return self.response(200, 'OK', json.dumps(response_data), {'Content-Type': 'application/json'})
                else:
                    return self.response(404, 'Not Found', json.dumps({"error": "Game not found"}), {'Content-Type': 'application/json'})
            except Exception as e:
                return self.response(500, 'Internal Server Error', str(e), {})
        
        if object_address == '/':
            return self.response(200,'OK','Coup Game Server is running', {})
        return self.response(404,'Not Found','',{})

    def http_post(self, object_address, body):
        try:
            post_data = json.loads(body)
        except json.JSONDecodeError:
            return self.response(400, 'Bad Request', json.dumps({"error": "Invalid JSON"}), {'Content-Type': 'application/json'})

        if object_address == '/matchmake':
            player_name = post_data.get('name', 'Anon')
            game_id, player_id = self.server_manager.find_or_create_game(player_name)
            if player_id is not None:
                response_data = {'player_id': player_id, 'game_id': game_id}
                return self.response(200, 'OK', json.dumps(response_data), {'Content-Type': 'application/json'})
            else:
                return self.response(500, 'Internal Server Error', json.dumps({'error': 'Failed to join game'}), {'Content-Type': 'application/json'})

        if object_address in ['/action', '/quit']:
            game_id = post_data.get('game_id')
            game = self.server_manager.get_game(game_id)
            if game:
                if object_address == '/action':
                    game.handle_action(post_data)
                elif object_address == '/quit':
                    game.eliminate_player(post_data.get('player_id'))
                return self.response(200, 'OK', json.dumps({"status": "ok"}), {'Content-Type': 'application/json'})
            else:
                return self.response(404, 'Not Found', json.dumps({"error": "Game not found"}), {'Content-Type': 'application/json'})
        
        return self.response(404,'Not Found','',{})
