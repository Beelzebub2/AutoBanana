


def fire(text):
        '''The function `fire` takes a text input and applies a color fade effect to each line,
        transitioning from green to black.

        Parameters
        ----------
        text
            The `fire` method takes a `text` input, which is a string containing one or more lines of text.
        The method then processes each line of text to create a "fire effect" by changing the color of
        the text from green to red gradually. The method returns the processed text with the

        Returns
        -------
            The `fire` method takes a text input, splits it into lines, and then generates a colored output
        where each line has a fading green color effect. The color starts as bright green (RGB 255, 250,
        0) and gradually fades to darker green as the lines progress. The method returns the formatted
        text with the fading green effect applied.

        '''
        fade = ""
        green = 250
        for line in text.splitlines():
            fade += f"\033[38;2;255;{green};0m{line}\033[0m\n"
            green = max(0, green - 25)
        return fade

def ice(text):
    '''The `ice` function takes a text input and applies a fading blue color effect to each line of the
    text.

    Parameters
    ----------
    text
        The `ice` function takes a text input and applies a fading effect to it by changing the blue
    color component gradually from 255 to 0 as it goes through each line of the input text. The
    function then returns the text with the fading effect applied.

    Returns
    -------
        The `ice` function takes a text input and applies a fading effect to it by changing the blue
    color component gradually from 255 to 0. The function returns the input text with the fading
    effect applied using ANSI escape codes for colored text.

    '''
    fade = ""
    blue = 255
    for line in text.splitlines():
        fade += f"\033[38;2;0;{blue};255m{line}\033[0m\n"
        blue = max(0, blue - 25)
    return fade

def pinkneon(text):
    '''The function `pinkneon` takes a text input and creates a pink neon effect by fading the text
    color from white to blue.

    Parameters
    ----------
    text
        The `pinkneon` function takes a text input and creates a pink neon effect by fading the text
    color from pink to blue. The function iterates over each line of the input text, calculating the
    blue color value based on the line index, and then formats the text with ANSI escape codes to

    Returns
    -------
        The `pinkneon` function returns a string with the input text formatted with a pink neon color
    effect. Each line of the input text is displayed with a fading effect from pink to blue.

    '''
    fade = ""
    for index, line in enumerate(text.splitlines()):
        blue = max(255 - 20 * index, 0)
        fade += f"\033[38;2;255;0;{blue}m{line}\033[0m\n"
    return fade

def default_theme(text):
    return text