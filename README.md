    # SigmaOS-term

    Terminal launcher wrapper (foot/ghostty/kitty)

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/ptyxis-minted
- https://github.com/omacom/omaterm

    ## Design principles applied
    - **Separation of Concerns**
- **Data-Driven Design**
- **Defensive Programming**
- **Fail-Fast**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `launch-plan, profiles, font, keybinds`

    ```
    $ sigma-term launch-plan --backend kitty --title dev -- htop
kitty --title=dev -e htop
$ sigma-term launch-plan --backend alacritty --title logs
alacritty -t logs
$ sigma-term profiles
$ sigma-term font --backend foot --family "JetBrainsMono Nerd Font" --size 12
$ sigma-term keybinds --backend kitty --bind new_tab=ctrl+shift+t

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
