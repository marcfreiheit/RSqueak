as yet unclassified
setUp
	| gen |
	self
		numMatches: 1000000;
		numPlayers: 100000;
		seed: 42.
	gen := EloDataGenerator new seed: (self seed).
	DBObject beginTransaction.
	data := gen generatePlayers: self numPlayers matches: self numMatches.
	DBObject endTransaction.