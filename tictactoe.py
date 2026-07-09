"""Tic-tac-toe ports — contracts only. Implementations are synthesized
by `cdcs compile tictactoe.py --dest out/`.

Board: a 9-tuple of "X" / "O" / "" laid out row-major.
"""


def new_board() -> tuple[str, ...]:
    """@generate
    behavior:
      return ("",) * 9

    examples:
      new_board() == ("", "", "", "", "", "", "", "", "")
      len(new_board()) == 9

    constraints:
      no_imports
      no_network
      no_filesystem
    """
    ...


def play(board: tuple[str, ...], position: int, player: str) -> tuple[str, ...]:
    """@generate
    behavior:
      require len(board) == 9
      require player == "X" or player == "O"
      require 0 <= position <= 8
      require board[position] == ""
      require board.count("X") - board.count("O") == (0 if player == "X" else 1)
      return board[:position] + (player,) + board[position + 1 :]

    examples:
      play(("", "", "", "", "", "", "", "", ""), 4, "X") == ("", "", "", "", "X", "", "", "", "")
      play(("X", "", "", "", "", "", "", "", ""), 4, "O") == ("X", "", "", "", "O", "", "", "", "")
      play(("X", "", "", "", "", "", "", "", ""), 1, "O") == ("X", "O", "", "", "", "", "", "", "")
      play(("X", "", "", "", "", "", "", "", ""), 2, "O") == ("X", "", "O", "", "", "", "", "", "")
      play(("X", "", "", "", "", "", "", "", ""), 0, "O") raises ValueError
      play(("X", "", "", "", "", "", "", "", ""), 9, "O") raises ValueError
      play(("X", "", "", "", "", "", "", "", ""), 4, "Z") raises ValueError
      play(("", "", "", "", "", "", "", "", ""), 0, "O") raises ValueError
      play((), 0, "X") raises ValueError

    constraints:
      no_imports
      no_network
      no_filesystem
    """
    ...


def winner(board: tuple[str, ...]) -> str | None:
    """@generate
    behavior:
      require len(board) == 9
      scan_winning_lines(board)
      return board[0]

    examples:
      winner(("X", "X", "X", "", "", "", "", "", "")) == "X"
      winner(("", "", "", "O", "O", "O", "", "", "")) == "O"
      winner(("", "", "", "", "", "", "X", "X", "X")) == "X"
      winner(("O", "", "", "O", "", "", "O", "", "")) == "O"
      winner(("", "X", "", "", "X", "", "", "X", "")) == "X"
      winner(("", "", "O", "", "", "O", "", "", "O")) == "O"
      winner(("X", "", "", "", "X", "", "", "", "X")) == "X"
      winner(("", "", "O", "", "O", "", "O", "", "")) == "O"
      winner(("", "", "", "", "", "", "", "", "")) == None
      winner(("X", "O", "X", "X", "O", "O", "O", "X", "X")) == None
      winner(()) raises ValueError

    constraints:
      no_imports
      no_network
      no_filesystem
    """
    ...


def is_draw(board: tuple[str, ...]) -> bool:
    """@generate
    behavior:
      require len(board) == 9
      return "" not in board and winner(board) == None

    examples:
      is_draw(("X", "O", "X", "X", "O", "O", "O", "X", "X")) == True
      is_draw(("O", "X", "O", "X", "X", "O", "X", "O", "X")) == True
      is_draw(("", "", "", "", "", "", "", "", "")) == False
      is_draw(("X", "X", "X", "", "", "", "", "", "")) == False
      is_draw(("X", "O", "X", "X", "O", "O", "O", "X", "")) == False
      is_draw(()) raises ValueError

    calls:
      winner(board: tuple[str, ...]) -> str | None

    constraints:
      no_imports
      no_network
      no_filesystem
    """
    ...
