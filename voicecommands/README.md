# VoiceCommands Cog

A Red-Bot cog that enables voice control for Discord audio playback using speech recognition and wake word detection.

## Features

- **Wake Word Detection**: Responds to "Hey Maki" or just "Maki"
- **Simple Voice Commands**: Control audio playback with natural speech
- **Offline Processing**: Uses local speech recognition for privacy
- **Audio Cog Integration**: Works seamlessly with Red-Bot's Audio cog
- **Configurable**: Customizable wake words and commands per server

## Supported Commands

After saying the wake word ("Hey Maki"), you can use these commands:

- **Pause**: "pause", "stop playing", "halt"
- **Resume**: "resume", "continue", "play"  
- **Stop**: "stop", "end", "quit"
- **Disconnect**: "disconnect", "leave", "bye"

## Prerequisites

This cog requires additional Python packages that are not included with Red-Bot by default:

```bash
pip install py-cord SpeechRecognition openwakeword numpy librosa
```

**Important**: This cog requires **py-cord** (Pycord) instead of the standard discord.py library for voice recording capabilities. You may need to modify your Red-Bot installation to use py-cord.

## Installation

1. Install the required dependencies (see Prerequisites above)
2. Add the cog to your Red-Bot instance
3. Load the cog: `[p]load voicecommands`
4. Enable voice commands: `[p]voicecommands enable`

## Usage

1. **Enable the cog**: `[p]voicecommands enable`
2. **Join a voice channel** where you want to use voice commands
3. **Start listening**: `[p]voicecommands start` 
4. **Use voice commands**: Say "Hey Maki, pause" or "Maki, disconnect"
5. **Stop listening**: `[p]voicecommands stop`

## Commands

- `[p]voicecommands` - Show status and configuration
- `[p]voicecommands enable` - Enable voice commands for the server
- `[p]voicecommands disable` - Disable voice commands for the server  
- `[p]voicecommands start` - Start listening for voice commands
- `[p]voicecommands stop` - Stop listening for voice commands
- `[p]voicecommands test` - Test if dependencies are properly installed

## Configuration

The cog stores configuration per server including:

- Enabled/disabled status
- Wake word sensitivity threshold
- Command mappings
- Recording timeout settings

## Architecture

### Voice Processing Flow

1. **Wake Word Detection**: Continuously monitors audio for "Hey Maki"
2. **Command Recording**: After wake word detection, records 3 seconds of audio
3. **Speech Recognition**: Converts recorded audio to text using offline recognition
4. **Command Processing**: Matches recognized text to configured commands
5. **Audio Control**: Calls appropriate Audio cog methods

### Audio Cog Integration

The VoiceCommands cog integrates with Red-Bot's Audio cog by:

- Getting the Audio cog instance: `self.bot.get_cog("Audio")`
- Calling Audio cog methods for pause, resume, stop operations
- Managing voice channel connections cooperatively

### Conflict Resolution

- Voice recording sessions are temporary (3 seconds max)
- Coordinates with Audio cog to avoid connection conflicts
- Automatically stops listening when disconnecting from voice

## Technical Details

### Dependencies

- **py-cord**: Discord library fork with voice recording support
- **SpeechRecognition**: Wrapper library for various speech recognition APIs
- **openwakeword**: Offline wake word detection framework
- **numpy**: Numerical computing for audio processing
- **librosa**: Audio analysis library

### Limitations

- Requires py-cord instead of standard discord.py
- May have conflicts with other voice-recording applications
- Offline recognition accuracy varies with audio quality
- Currently supports English commands only

## Development Status

This is a proof-of-concept implementation. The core voice recording and wake word detection functionality is structured but requires:

1. Implementation of actual voice recording from Discord voice channels
2. Integration with py-cord's voice recording API
3. Fine-tuning of wake word detection sensitivity
4. Enhanced error handling and recovery

## Privacy

All voice processing is done locally on the server. No audio data is transmitted to external services or stored permanently.

## Troubleshooting

### Dependencies Not Available
```
pip install py-cord SpeechRecognition openwakeword numpy librosa
```

### Voice Commands Not Working
1. Ensure you're connected to a voice channel
2. Check that voice commands are enabled: `[p]voicecommands`
3. Verify Audio cog is loaded
4. Test dependencies: `[p]voicecommands test`

### Audio Conflicts
- Stop voice commands before using complex Audio cog features
- Restart the bot if voice connections become unstable

## Contributing

This cog is designed to be extensible. Future improvements could include:

- Multi-language support
- Custom wake word training
- Voice response/confirmation
- Advanced command parsing
- Integration with other cogs beyond Audio

## Authors

- Nero
- Claude