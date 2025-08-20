# Twitter Auto Bot

An intelligent Twitter automation tool that tracks tweets from target accounts and automatically generates thoughtful replies and quote tweets using OpenAI GPT-4.

## Features

- 🔄 **Automated Tweet Polling**: Monitors target accounts every 5 minutes
- 🤖 **AI-Powered Responses**: Generates human-like replies and quote tweets using GPT-4
- 📊 **Engagement Tracking**: Monitors likes, retweets, and replies on posted content
- 🎯 **Smart Filtering**: Only responds to suitable tweets using intelligent filtering
- 📈 **Performance Learning**: Improves prompts using top-performing tweets as examples
- 🗄️ **Database Logging**: Comprehensive logging of all interactions and metrics
- ⚡ **Real-time Operation**: Runs continuously with configurable intervals

## Prerequisites

- Python 3.8+
- Twitter API v2 access with OAuth2 credentials
- OpenAI API key
- Supabase account and database

## Installation

1. **Clone and setup**:
   ```bash
   cd twitter-auto
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API credentials
   ```

3. **Set up your environment variables**:
   ```env
   # Twitter API OAuth2 credentials
   TWITTER_CONSUMER_KEY=your_consumer_key
   TWITTER_CONSUMER_SECRET=your_consumer_secret
   TWITTER_ACCESS_TOKEN=your_access_token
   TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
   TWITTER_BEARER_TOKEN=your_bearer_token

   # OpenAI API
   OPENAI_API_KEY=your_openai_api_key

   # Supabase
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key

   # Configuration
   TARGET_ACCOUNTS=elonmusk,sundarpichai,satyanadella
   POLL_INTERVAL_MINUTES=5
   ENGAGEMENT_CHECK_HOURS=2
   ```

## Usage

### Test Configuration
```bash
python twitter_bot.py test
```

### Run Once (Single Cycle)
```bash
python twitter_bot.py once
```

### Start Continuous Monitoring
```bash
python twitter_bot.py start
```

### View Statistics
```bash
python twitter_bot.py stats
```

### Update Engagement Metrics
```bash
python twitter_bot.py engagement
```

### View Configuration
```bash
python twitter_bot.py config
```

## Command Line Options

- `start` - Run continuously with scheduled polling
- `once` - Run a single polling and processing cycle
- `stats` - Display current statistics and performance metrics
- `engagement` - Manually update engagement metrics for all tweets
- `config` - Display current configuration
- `test` - Test all API connections
- `--log-level` - Set logging level (DEBUG, INFO, WARNING, ERROR)

## Database Schema

The tool automatically creates two main tables in your Supabase database:

### tweets
- `id` - Primary key
- `tweet_id` - Unique Twitter tweet ID
- `original_tweet` - Text of the original tweet
- `response` - Generated response text
- `type` - Response type (reply or quote_rt)
- `time_posted` - When the response was posted
- `author_username` - Original tweet author
- `created_at` - Record creation timestamp

### engagement_metrics
- `id` - Primary key
- `tweet_id` - Reference to tweets table
- `likes` - Number of likes
- `retweets` - Number of retweets
- `replies` - Number of replies
- `timestamp` - When metrics were recorded

## How It Works

1. **Polling**: Every 5 minutes, the bot checks target accounts for new tweets
2. **Filtering**: Tweets are filtered for suitability (length, content, engagement)
3. **Response Generation**: GPT-4 generates contextually appropriate replies or quote tweets
4. **Posting**: Responses are automatically posted to Twitter
5. **Logging**: All interactions are saved to the database
6. **Engagement Tracking**: Metrics are updated every 2 hours
7. **Learning**: Top-performing tweets become examples for future responses

## Response Types

- **Replies**: Direct responses to tweets that add value to the conversation
- **Quote Tweets**: Commentary that provides additional perspective or insight

## Safety Features

- Smart filtering prevents responses to inappropriate content
- Response validation ensures quality and appropriateness
- Rate limiting respects Twitter API limits
- Comprehensive error handling and logging
- Graceful shutdown on interruption

## Monitoring

Logs are automatically created in the `logs/` directory:
- `twitter_bot.log` - All activity logs
- `twitter_bot_errors.log` - Error logs only
- `twitter_bot_activity.log` - Successful operations only

## Deployment

For production deployment:

1. **Using cron** (alternative to continuous mode):
   ```bash
   # Add to crontab for every 5 minutes
   */5 * * * * cd /path/to/twitter-auto && python twitter_bot.py once
   ```

2. **Using systemd** (Linux):
   ```bash
   # Create a systemd service file
   sudo systemctl enable twitter-bot
   sudo systemctl start twitter-bot
   ```

3. **Using Docker**:
   ```bash
   # Build and run container
   docker build -t twitter-bot .
   docker run -d --env-file .env twitter-bot
   ```

## Troubleshooting

- **Twitter API errors**: Check your API credentials and rate limits
- **OpenAI errors**: Verify your API key and billing status
- **Database errors**: Ensure Supabase URL and key are correct
- **No tweets found**: Check that target accounts are public and posting
- **Rate limiting**: The bot handles rate limits automatically with delays

## Configuration Tips

- Start with 2-3 target accounts to test the system
- Monitor the logs to understand response patterns
- Adjust polling intervals based on account activity
- Review generated responses in the database to fine-tune prompts

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License.