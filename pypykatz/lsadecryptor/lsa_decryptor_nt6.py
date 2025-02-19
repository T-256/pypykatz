#!/usr/bin/env python3
#
# Author:
#  Tamas Jos (@skelsec)
#


import traceback
from pypykatz import logger
from pypykatz.commons.generics import hexdump
from unicrypto.symmetric import TDES, AES, MODE_CFB, MODE_CBC
from pypykatz.lsadecryptor.package_commons import PackageDecryptor

class LsaDecryptor_NT6(PackageDecryptor):
	def __init__(self, reader, decryptor_template, sysinfo):
		super().__init__('LsaDecryptor', None, sysinfo, reader)
		self.decryptor_template = decryptor_template
		self.iv = None
		self.aes_key = None
		self.des_key = None
		
		self.acquire_crypto_material()
		
	def acquire_crypto_material(self):
		self.log('Acquireing crypto stuff...')
		sigpos = self.find_signature()
		self.reader.move(sigpos)
		data = self.reader.peek(0x50)
		self.log('Memory looks like this around the signature\n%s' % hexdump(data, start = sigpos))
		self.iv = self.get_IV(sigpos)
		self.des_key = self.get_des_key(sigpos)
		self.aes_key = self.get_aes_key(sigpos)
		
	def get_des_key(self, pos):
		self.log('Acquireing DES key...')
		return self.get_key(pos, self.decryptor_template.key_pattern.offset_to_DES_key_ptr)
		
	def get_aes_key(self, pos):
		self.log('Acquireing AES key...')
		return self.get_key(pos, self.decryptor_template.key_pattern.offset_to_AES_key_ptr)
		
	def find_signature(self):
		self.log('Looking for main struct signature in memory...')
		fl = self.reader.find_in_module('lsasrv.dll', self.decryptor_template.key_pattern.signature, find_first = True)
		if len(fl) == 0:
			logger.debug('signature not found! %s' % self.decryptor_template.key_pattern.signature.hex())
			raise Exception('LSA signature not found!')
			
		self.log('Found candidates on the following positions: %s' % ' '.join(hex(x) for x in fl))
		self.log('Selecting first one @ 0x%08x' % fl[0])
		return fl[0]

	def get_IV(self, pos):
		self.log('Reading IV')

		#### TEST!!!!
		#if hasattr(self.sysinfo, 'IV_OFFSET'):
		#	ptr_iv = self.reader.get_ptr_with_offset(pos + self.sysinfo.IV_OFFSET)
		#	self.reader.move(ptr_iv)
		#	data = self.reader.read(self.decryptor_template.key_pattern.IV_length)
		#	self.log('IV data: %s' % hexdump(data))
		#	return data
		
		ptr_iv = self.reader.get_ptr_with_offset(pos + self.decryptor_template.key_pattern.offset_to_IV_ptr)
		#self.log('IV pointer takes us to 0x%08x' % ptr_iv)
		self.reader.move(ptr_iv)
		data = self.reader.read(self.decryptor_template.key_pattern.IV_length)
		self.log('IV data: %s' % hexdump(data))
		return data

	def get_key(self, pos, key_offset):
		ptr_key = self.reader.get_ptr_with_offset(pos + key_offset)
		self.log('key handle pointer is @ 0x%08x' % ptr_key)
		ptr_key = self.reader.get_ptr(ptr_key)
		self.log('key handle is @ 0x%08x' % ptr_key)
		self.reader.move(ptr_key)
		data = self.reader.peek(0x50)
		self.log('BCRYPT_HANLE_KEY_DATA\n%s' % hexdump(data, start = ptr_key))
		kbhk = self.decryptor_template.key_handle_struct(self.reader)
		if kbhk.verify():
			ptr_key = kbhk.ptr_key.value
			self.reader.move(ptr_key)
			data = self.reader.peek(0x50)
			self.log('BCRYPT_KEY_DATA\n%s' % hexdump(data, start = ptr_key))
			kbk = kbhk.ptr_key.read(self.reader, self.decryptor_template.key_struct)
			self.log('HARD_KEY SIZE: 0x%x' % kbk.size)
			if kbk.verify():
				self.log('HARD_KEY data:\n%s' % hexdump(kbk.hardkey.data))
				return kbk.hardkey.data

	def decrypt(self, encrypted, segment_size=128):
		# TODO: NT version specific, move from here in subclasses.
		cleartext = b''
		size = len(encrypted)
		if size:
			if size % 8:
				logger.debug('AES-CFB - %s' % size)
				if not self.aes_key or not self.iv:
					return cleartext
				cipher = AES(self.aes_key, MODE_CFB, IV = self.iv, segment_size=segment_size)
				cleartext = cipher.decrypt(encrypted)
			else:
				logger.debug('TDES - size %s' % size)
				if not self.des_key or not self.iv:
					return cleartext
				cipher = TDES(self.des_key, MODE_CBC, self.iv[:8])
				cleartext = cipher.decrypt(encrypted)
		return cleartext

	def dump(self):
		self.log('Recovered LSA encryption keys\n')
		self.log('IV ({}): {}'.format(len(self.iv), self.iv.hex()))
		self.log('DES_KEY ({}): {}'.format(len(self.des_key), self.des_key.hex()))
		self.log('AES_KEY ({}): {}'.format(len(self.aes_key), self.aes_key.hex()))