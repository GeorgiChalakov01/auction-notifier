document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.add-field').forEach(button => {
        button.addEventListener('click', function() {
            const target = this.dataset.target;
            const container = document.getElementById(target);
            
            const newInputGroup = document.createElement('div');
            newInputGroup.className = 'input-group mb-2';
            
            const newInput = document.createElement('input');
            newInput.type = 'text';
            newInput.name = this.previousElementSibling.name;
            newInput.className = 'form-control';
            
            const newButton = document.createElement('button');
            newButton.type = 'button';
            newButton.className = 'btn btn-outline-secondary add-field';
            newButton.dataset.target = target;
            newButton.innerHTML = '<i class="bi bi-plus"></i>';
            
            newInputGroup.appendChild(newInput);
            newInputGroup.appendChild(newButton);
            container.appendChild(newInputGroup);
            
            newButton.addEventListener('click', function() {
                this.parentElement.remove();
            });
        });
    });
});
