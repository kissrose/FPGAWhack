# 
# Copyright 2013 Jeff Bush
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

import sys

class CodeGenerator:
	def __init__(self, filename):
		self.operandStack = []
		self.freeRegisters = [ x for x in range(7, -1, -1) ]
		self.outputFile = open(filename, 'w')
		self.numInstructions = 0

	def pushConstant(self, value):
		self.operandStack += [ ('const', value) ]

	def pushVariableRef(self, index):
		self.operandStack += [ ('freg', index ) ]

	def doOp(self, operation):
		type2, op2 = self.operandStack.pop()
		type1, op1 = self.operandStack.pop()

		if type1 == 'const':
			# If the first operator is a constant, copy it into a register
			tmpReg = self._allocateTemporary()
			self._emitMicroInstruction(8, tmpReg, 0, 0, 1, op1)
			type1 = 'reg'
			op1 = tmpReg

		# Free up temporary registers, allocate a result reg
		if type2 == 'reg': self._freeTemporary(op2)
		if type1 == 'reg': self._freeTemporary(op1)
		resultReg = self._allocateTemporary()
		self.operandStack += [ ('reg', resultReg)]
		if type2 == 'const':
			self._emitMicroInstruction(operation, resultReg, op1, 0, 1, op2)
		else:
			self._emitMicroInstruction(operation, resultReg, op1, op2, 0, 0)

	def saveResult(self):
		# Emit an instruction to move into the result register
		type, op = self.operandStack.pop()
		if type == 'reg' or type == 'freg':
			self._emitMicroInstruction(0, 11, op, op, 0, 0)
		elif type == 'const':
			self._emitMicroInstruction(8, 11, 0, 0, 1, op)	# Constant
		else:
			raise Exception('internal error: bad type on operand stack')

		# Pad the remaining instructions with NOPs.
		for i in range(self.numInstructions, 16):
			self.outputFile.write('0000000000000\n')

		self.outputFile.close()

	def _emitMicroInstruction(self, opcode, dest, srca, srcb, isConst, constVal):
		self.numInstructions += 1
		if self.numInstructions == 16:
			raise Exception('formula too complex: exceeded instruction memory')
			
		self.outputFile.write('%013x\n' % ((dest << 45) | (srca << 41) | (srcb << 37) | (opcode << 33) | (isConst << 32) | constVal))

		# Pretty print operation
		pretty = [ 'and', 'xor', 'or', 'add', 'sub', 'mul', 'shl', 'shr', 'mov' ]
		if isConst:
			print '%s r%d, r%d, #%d' % (pretty[opcode], dest, srca, constVal)
		else:
			print '%s r%d, r%d, r%d' % (pretty[opcode], dest, srca, srcb)

	def _allocateTemporary(self):
		if len(self.freeRegisters) == 0:
			raise Exception('formula too complex: out of registers')
		else:
			return self.freeRegisters.pop()
		
	def _freeTemporary(self, val):
		self.freeRegisters += [ val ]

class Scanner:
	def __init__(self, stream):
		self.pushBackChar = None
		self.pushBackToken = False
		self.lastToken = None
		self.stream = stream

	def pushBack(self):
		self.pushBackToken = True

	def nextToken(self):
		if self.pushBackToken:
			self.pushBackToken = False
			return self.lastToken
	
		# Consume whitespace
		ch = self._nextChar()
		while ch.isspace():
			ch = self._nextChar()
	
		# Get next token
		if ch == '':
			# End of string
			self.lastToken = None
		elif ch.isdigit():
			lookahead = self._nextChar()
			if lookahead == '':
				self.lastToken = None
			elif lookahead == 'x':
				# Parse a hexadecimal number
				number = 0
				while True:
					ch = self._nextChar()
					if ch >= 'A' and ch <= 'F':
						number = (number * 16) + (ord(ch) - ord('A') + 10)
					elif ch >= 'a' and ch <= 'f':
						number = (number * 16) + (ord(ch) - ord('a') + 10)
					elif ch.isdigit():
						number = (number * 16) + (ord(ch) - ord('0'))
					else:
						self._pushBackChar(ch)
						break

				self.lastToken = number
			else:
				# Parse a decimal number
				self._pushBackChar(lookahead)
				number = 0
				while ch.isdigit():
					number = (number * 10) + (ord(ch) - ord('0'))
					ch = self._nextChar()

				self._pushBackChar(ch)
				self.lastToken = number
		elif ch == '<':
			lookahead = self._nextChar()
			if lookahead == '<':
				self.lastToken = '<<'
			else:
				self._pushBackChar()
				self.lastToken = '<'
		elif ch == '>':
			lookahead = self._nextChar()
			if lookahead == '>':
				self.lastToken = '>>'
			else:
				self._pushBackChar()
				self.lastToken = '>'
		elif ch.isalpha():
			strval = ch
			while True:
				ch = self._nextChar()
				if ch.isalnum():
					strval += ch
				else:
					self._pushBackChar(ch)
					break
					
			self.lastToken = strval
		else:
			# Single character symbolic token
			self.lastToken = ch
			
		return self.lastToken

	def _nextChar(self):
		if self.pushBackChar:
			ch = self.pushBackChar
			self.pushBackChar = None
			return ch
		else:
			return self.stream.read(1)

	def _pushBackChar(self, ch):
		self.pushBackChar = ch

class Parser:
	def __init__(self, inputStream, generator):
		self.scanner = Scanner(inputStream)
		self.generator = generator

	def parse(self):
		self._parseExpression()
		self.generator.saveResult()

	def _parseExpression(self):	
		self._parsePrimaryExpression()
		self._parseInfixExpression(0)

	BUILTIN_VARS = {
		'x' : 8,
		'ix' : 8,
		'y' : 9,
		'iy' : 9,
		'f' : 10
	}

	def _parsePrimaryExpression(self):
		tok = self.scanner.nextToken()
		if tok == '(':
			self._parseExpression()
			tok = self.scanner.nextToken()
			if tok != ')':
				raise Exception('parse error: expected )')
		elif isinstance(tok, int) or isinstance(tok, long):
			self.generator.pushConstant(tok)
		elif tok in self.BUILTIN_VARS:
			self.generator.pushVariableRef(self.BUILTIN_VARS[tok])
		else:
			raise Exception('unexpected: ' + tok)

	# Operator lookup table
	# (precedence, opcode)
	OPERATORS = {
		'&' : ( 3, 0 ),
		'^' : ( 2, 1 ),
		'|' : ( 1, 2 ),
		'+' : ( 5, 3 ),
		'-' : ( 5, 4 ),
		'*' : ( 6, 5 ),
		'<<' : ( 4, 6 ),
		'>>' : ( 4, 7 ),
#		'/' : ( 7, -1 )
	}

	def _parseInfixExpression(self, minPrecedence):
		while True:	# Reduce loop
			outerOp = self.scanner.nextToken()
			if outerOp == None:
				break

			if outerOp not in self.OPERATORS:
				self.scanner.pushBack()
				break
			
			outerPrecedence, outerOpcode = self.OPERATORS[outerOp]
			if outerPrecedence < minPrecedence:
				self.scanner.pushBack()
				break

			self._parsePrimaryExpression()
			while True:	# Shift loop
				lookahead = self.scanner.nextToken()			
				if lookahead == None:
				 	break
				 
				self.scanner.pushBack()
				if lookahead not in self.OPERATORS:
					break
					
				innerPrecedence, _ignore = self.OPERATORS[lookahead]
				if innerPrecedence <= outerPrecedence:
					break
					
				self._parseInfixExpression(innerPrecedence)

			self.generator.doOp(outerOpcode)

p = Parser(sys.stdin, CodeGenerator('microcode.hex'))
p.parse()

