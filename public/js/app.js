let notYetSunk = true;
let shipNum1 = crypto.randomInt(1, 4);
let shipNum2 = shipNum1 + 1;
let shipNum3 = shipNum2 + 1;
const shipLocations = [shipNum1, shipNum2, shipNum3];
let hits = 0;
let guesses = 0;
while (notYetSunk) {
  let userInput = Number(prompt("Where is the ship? (1-7)"));
  if (
    Number.isInteger(userInput) &&
    userInput >= 1 &&
    userInput <= 7 &&
    !isNaN(userInput)
  ) {
    guesses++;
    if (shipLocations.includes(userInput)) {
      alert("You hit the ship!");
      hits++;
      notYetSunk = true;
      if (hits === shipLocations.length) {
        alert("You sank the ship!");
        notYetSunk = false;
      }
    } else {
      alert("You missed!");
    }
  } else {
    alert("Invalid input. Please enter a number between 1 and 7.");
  }
}
alert("Game over! You made " + guesses + " guesses.");
