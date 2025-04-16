# TODO

- [x] Add a setting to disable the profanity filter completely
- [ ] Timeouts
  - [ ] Fall back to persona name and show title as `artist` and `title`, respectively, if the timeout for a song is reached
  - [ ] Add a setting to disable the song timeout completely (`duration` from Spinitron will not be used - all RT+ packets will persist until the next is sent)
  - [ ] If a RT+ packet has timed out, the `TEXT` field should also be cleared and something else should be sent (e.g. a bumper)
- [ ] Implement "do-not-notify" lists: Allow translations (like unidecoding or profanity filtering) without sending notifications to Discord.
- [ ] Implement "do-not-censor" lists: Words that bypass profanity filters.
- [ ] Discord commands/callback buttons: Quickly manage lists from Discord itself (/banword WORD, button callbacks).
