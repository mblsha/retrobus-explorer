use anyhow::{anyhow, Result};

pub const DISPLAY_WIDTH: usize = 240;
pub const DISPLAY_HEIGHT: usize = 32;
const CHIP_WIDTH: usize = 64;
const CHIP_PAGES: usize = 8;
const PAGE_HEIGHT: usize = 8;
const CHIP_HEIGHT: usize = CHIP_PAGES * PAGE_HEIGHT;
const LEFT_VISIBLE_WIDTH: usize = 56;
const RIGHT_VISIBLE_WIDTH: usize = 64;

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
enum Instruction {
    OnOff,
    SetYAddress,
    SetPage,
    StartLine,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
enum ChipSelect {
    Both,
    Right,
    Left,
}

#[derive(Copy, Clone, Debug)]
struct Command {
    cs: ChipSelect,
    instr: Option<Instruction>,
    data: u8,
}

#[derive(Clone, Debug, Default)]
struct ChipState {
    on: bool,
    busy: bool,
    start_line: u8,
    page: u8,
    y_address: u8,
}

#[derive(Clone, Debug)]
struct Chip {
    state: ChipState,
    vram: [[u8; CHIP_WIDTH]; CHIP_PAGES],
}

impl Default for Chip {
    fn default() -> Self {
        Self {
            state: ChipState::default(),
            vram: [[0; CHIP_WIDTH]; CHIP_PAGES],
        }
    }
}

impl Chip {
    fn write_instruction(&mut self, instr: Instruction, data: u8) {
        self.state.busy = true;
        match instr {
            Instruction::OnOff => self.state.on = (data & 1) != 0,
            Instruction::SetYAddress => self.state.y_address = data & 0x3f,
            Instruction::SetPage => self.state.page = data & 0x07,
            Instruction::StartLine => self.state.start_line = data & 0x3f,
        }
    }

    fn write_data(&mut self, data: u8) {
        self.state.busy = true;
        let page = (self.state.page as usize) % CHIP_PAGES;
        let column = (self.state.y_address as usize) % CHIP_WIDTH;
        self.vram[page][column] = data;
        self.state.y_address = ((column + 1) % CHIP_WIDTH) as u8;
    }
}

#[derive(Clone, Debug, Default)]
pub struct LcdModel {
    chips: [Chip; 2],
}

impl LcdModel {
    pub fn apply_raw(&mut self, address: u32, value: u8) -> Result<()> {
        let command = parse_command(address, value)?;
        let indices: &[usize] = match command.cs {
            ChipSelect::Both => &[0, 1],
            ChipSelect::Right => &[1],
            ChipSelect::Left => &[0],
        };
        for &idx in indices {
            let chip = &mut self.chips[idx];
            if let Some(instr) = command.instr {
                chip.write_instruction(instr, command.data);
            } else {
                chip.write_data(command.data);
            }
        }
        Ok(())
    }

    pub fn render_monochrome(&self) -> Vec<u8> {
        let mut pixels = vec![0u8; DISPLAY_WIDTH * DISPLAY_HEIGHT];

        for y in 0..DISPLAY_HEIGHT {
            for x in 0..RIGHT_VISIBLE_WIDTH {
                set_pixel(&mut pixels, x, y, chip_pixel(&self.chips[1], x, y));
            }

            for x in 0..LEFT_VISIBLE_WIDTH {
                set_pixel(
                    &mut pixels,
                    RIGHT_VISIBLE_WIDTH + x,
                    y,
                    chip_pixel(&self.chips[0], x, y),
                );
            }

            for x in 0..LEFT_VISIBLE_WIDTH {
                let source_x = LEFT_VISIBLE_WIDTH - 1 - x;
                set_pixel(
                    &mut pixels,
                    RIGHT_VISIBLE_WIDTH + LEFT_VISIBLE_WIDTH + x,
                    y,
                    chip_pixel(&self.chips[0], source_x, CHIP_HEIGHT / 2 + y),
                );
            }

            for x in 0..RIGHT_VISIBLE_WIDTH {
                let source_x = RIGHT_VISIBLE_WIDTH - 1 - x;
                set_pixel(
                    &mut pixels,
                    RIGHT_VISIBLE_WIDTH + LEFT_VISIBLE_WIDTH * 2 + x,
                    y,
                    chip_pixel(&self.chips[1], source_x, CHIP_HEIGHT / 2 + y),
                );
            }
        }

        pixels
    }
}

fn set_pixel(buffer: &mut [u8], x: usize, y: usize, on: bool) {
    buffer[y * DISPLAY_WIDTH + x] = if on { 0xff } else { 0x00 };
}

fn chip_pixel(chip: &Chip, x: usize, y: usize) -> bool {
    if !chip.state.on {
        return false;
    }
    let source_y = ((y + chip.state.start_line as usize) % CHIP_HEIGHT) as usize;
    let page = source_y / PAGE_HEIGHT;
    let bit = source_y % PAGE_HEIGHT;
    ((chip.vram[page][x] >> bit) & 1) != 0
}

fn parse_command(address: u32, value: u8) -> Result<Command> {
    let addr_hi = address & 0xf000;
    if addr_hi != 0x2000 && addr_hi != 0xa000 {
        return Err(anyhow!("not an LCD controller address: {address:#x}"));
    }

    let addr_lo = (address & 0x000f) as u8;
    let rw = (addr_lo & 0x01) != 0;
    if rw {
        return Err(anyhow!("read accesses are not LCD writes"));
    }

    let di_data = ((addr_lo >> 1) & 1) != 0;
    let cs = match (addr_lo >> 2) & 0b11 {
        0 => ChipSelect::Both,
        1 => ChipSelect::Right,
        2 => ChipSelect::Left,
        _ => return Err(anyhow!("chip select NONE")),
    };

    if di_data {
        return Ok(Command {
            cs,
            instr: None,
            data: value,
        });
    }

    let instr = match value >> 6 {
        0b00 => Instruction::OnOff,
        0b01 => Instruction::SetYAddress,
        0b10 => Instruction::SetPage,
        0b11 => Instruction::StartLine,
        _ => unreachable!(),
    };
    let data = match instr {
        Instruction::OnOff => value & 0x01,
        Instruction::SetYAddress | Instruction::StartLine => value & 0x3f,
        Instruction::SetPage => value & 0x07,
    };
    Ok(Command {
        cs,
        instr: Some(instr),
        data,
    })
}
