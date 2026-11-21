# 07 · Risks

Each risk has one owner and a fallback that is ready before Sunday.

| Risk | Owner | Prevention | Fallback on stage |
|---|---|---|---|
| Shoulder `j2` overload fault mid-move | ARM | Small steps, elbow tucked before lifting, current threshold raised | Power-cycle the follower, `home()`, continue from the last step |
| Camera bridge freezes | ARM | Joints from the motor bus, cameras read from `usbvideo` queues | Skip the `look` check once, Claude says so |
| Cup slips or is missed | ARM / BRAIN | Taught grip height per cup, load check on `j8` | This is the planned self-correction: look, explain, retry slower |
| Slow tool loop (long silences) | BRAIN | One tool per motion, images about 640 px, low effort or `/fast` | Claude speaks a short status line before long steps |
| Vision misclassifies a joint | BRAIN | 20+ labelled photos, few-shot prompt, eval script | Stage uses a prepared cold joint the check is known to catch |
| Voice fails in the hall | SCREEN | Clip-on mic, push-to-talk, noise test | Type the same sentence into Claude Code |
| Bench screen out of sync | SCREEN | State file written atomically, 250 ms polling | Arrow keys step the screen by hand |
| Live soldering runs long | BENCH | Only two parts live, the rest pre-soldered | Skip to the inspection with the second board |
| Glove finale does not inflate | BENCH | 10 test runs on battery | Show the backup video of the glove |
| Network or cloud outage | BRAIN / BENCH | Phone hotspot ready | Backup video recorded by Sun 12:00 |
| Pre-existing code questioned | BENCH | Disclose in README and submission | Point to NOTICE.md and the commit history |
