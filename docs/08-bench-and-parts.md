# 08 · Bench and parts

## Parts on the board (power stage of SOL-MIO v1.3)

Positions are board millimetres in the Altium frame (origin bottom left, y up).

| Order | Ref | Part | Package | Cup | Position | Polarity |
|---|---|---|---|---|---|---|
| fitted | U1 | 7805 regulator | TO-220 | — | (78.2, 81.3) | Metal tab toward the heatsink side |
| fitted | J2 | DC jack PJ-102A | THT | — | (92.6, 93.5) | Opening at the board edge |
| 1 | D2 | B5819WS Schottky diode, 1 A 40 V | SOD-323 | A1 | (82.0, 90.9) | Band to the lower pad (toward the 7805) |
| 2 | R1 | Power-LED resistor | 0603 | A2 | (87.6, 83.6) | None. **Value: fill in from the BOM** |
| 3 | D1 | Power LED | 1206 | A3 | (93.1, 83.6) | Cathode mark matches the silkscreen. **Colour: fill in** |
| 4 | C4 | 470 µF 25 V electrolytic | V-chip 8 × 10 | B1 | (74.7, 93.1) | Black stripe is minus; match the silkscreen |
| 5 | C13 | 330 µF 25 V electrolytic | V-chip 8 × 10 | B2 | (55.8, 93.1) | Black stripe is minus; match the silkscreen |

C4 and C13 sit on VIN, so they must be 25 V parts, never 10 V or 16 V. Cup B3 stays empty as a spare.

## Bench kit checklist (BENCH, before Sat 15:00)

- [ ] Stage board with U1 and J2 fitted from the underside
- [ ] Two rehearsal boards, one half built
- [ ] Fixture plate with four brass standoffs at the mounting holes, taped to the table
- [ ] Parts tray with cups A1–B2 loaded, plus a spare reel or strip of each part
- [ ] Handover zone marked with tape
- [ ] Soldering station, stand, sponge, flux pen, tweezers
- [ ] 12 V adapter with a centre-positive barrel plug
- [ ] Side camera on a clamp or tripod; wrist camera checked
- [ ] Bench screen monitor and its stand
- [ ] Finished SOL-MIO, glove, pump, battery pack for the finale
- [ ] Clip-on mic and a speaker; a foot pedal or big key for push-to-talk

## Before the demo

- [ ] Fill in the R1 value and the D1 colour in `screen/bench-screen/bench-screen.js` (`TARGETS`)
- [ ] Check every footprint on the bench screen against the real board; press R if it is upside down
- [ ] Check the capacitor and LED polarity marks against the real silkscreen
- [ ] Prepare one deliberately cold joint on the stage board for the inspection moment
